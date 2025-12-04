import threading
import time
import math
import copy
import enum
import random
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, NamedTuple, Iterable
from functools import total_ordering

# =============================================================================
# 1. CORE TYPES (Copied & Adapted from Agent)
# =============================================================================

@total_ordering
class Position:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    def __add__(self, other: 'Position') -> 'Position':
        return Position(self.x + other.x, self.y + other.y)

    def __sub__(self, other: 'Position') -> 'Position':
        return Position(self.x - other.x, self.y - other.y)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Position):
            return (self.x == other.x and self.y == other.y) or (self.is_null() and other.is_null())
        return False
    
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Position): return NotImplemented
        return (self.x, self.y) < (other.x, other.y)

    def __hash__(self) -> int:
        return hash((self.x, self.y))

    def is_valid(self) -> bool:
        return 0 <= self.x < 5 and 0 <= self.y < 5

    def is_null(self) -> bool:
        return not self.is_valid()
    
    def __repr__(self): return f"({self.x},{self.y})"

Position.Null = Position(-1, -1)

class PositionPair(NamedTuple):
    From: Position
    To: Position

class ReducedMoveInfo(NamedTuple):
    From: Position
    To: Position

@dataclass(frozen=True)
class MoveInfo:
    From: Position
    FromPiece: str
    To: Position
    ToPiece: str
    PromotionPiece: str
    EP: Position
    EPPiece: str
    IsPromotion: bool
    IsLegal: bool
    PreviousEnPassantTarget: Position
    NewEnPassantTarget: Position

    def to_reduced_move_info(self) -> ReducedMoveInfo:
        return ReducedMoveInfo(self.From, self.To)

MoveInfo.Default = MoveInfo(
    From=Position.Null, FromPiece='.', To=Position.Null, ToPiece='.',
    EP=Position.Null, EPPiece='.', PromotionPiece='.', IsPromotion=False,
    IsLegal=False, PreviousEnPassantTarget=Position.Null, NewEnPassantTarget=Position.Null
)

# =============================================================================
# 2. GAME STATE & ZOBRIST
# =============================================================================

class GameState:
    class Zobrist:
        _random = random.Random(12345) # Fixed seed for consistency
        zobrist_table: List[List[List[int]]] = []
        black_to_move: int = 0
        
        @staticmethod
        def _random_ulong() -> int:
            return GameState.Zobrist._random.getrandbits(64)

        @staticmethod
        def _initialize():
            if GameState.Zobrist.zobrist_table: return
            GameState.Zobrist.black_to_move = GameState.Zobrist._random_ulong()
            GameState.Zobrist.zobrist_table = [[[GameState.Zobrist._random_ulong() for _ in range(15)] for _ in range(5)] for _ in range(5)]
        
        @staticmethod
        def compute_hash(game: 'GameState') -> int:
            h = 0
            for i in range(5):
                for j in range(5):
                    piece = game.board[i][j]
                    if piece != '.':
                        piece_index = GameState.Zobrist.index_of(piece)
                        h ^= GameState.Zobrist.zobrist_table[i][j][piece_index]
            if not game.whiteToMove:
                h ^= GameState.Zobrist.black_to_move
            if game.enPassantTarget.is_valid():
                h ^= GameState.Zobrist.zobrist_table[game.enPassantTarget.x][game.enPassantTarget.y][12]
            return h

        @staticmethod
        def update_hash(current: int, move: MoveInfo) -> int:
            from_idx = GameState.Zobrist.index_of(move.FromPiece)
            to_idx = GameState.Zobrist.index_of(move.ToPiece)
            ep_idx = GameState.Zobrist.index_of(move.EPPiece)
            promo_idx = GameState.Zobrist.index_of(move.PromotionPiece)

            current ^= GameState.Zobrist.zobrist_table[move.From.x][move.From.y][from_idx]
            if to_idx != -1:
                current ^= GameState.Zobrist.zobrist_table[move.To.x][move.To.y][to_idx]
            if move.EPPiece != '.':
                current ^= GameState.Zobrist.zobrist_table[move.EP.x][move.EP.y][ep_idx]
            current ^= GameState.Zobrist.zobrist_table[move.To.x][move.To.y][promo_idx]
            current ^= GameState.Zobrist.black_to_move

            if move.PreviousEnPassantTarget.is_valid():
                current ^= GameState.Zobrist.zobrist_table[move.PreviousEnPassantTarget.x][move.PreviousEnPassantTarget.y][14]
            if move.NewEnPassantTarget.is_valid():
                current ^= GameState.Zobrist.zobrist_table[move.NewEnPassantTarget.x][move.NewEnPassantTarget.y][14]
            return current
        
        @staticmethod
        def pass_turn(current: int, en_passant: Position) -> int:
            if en_passant.is_valid():
                current ^= GameState.Zobrist.zobrist_table[en_passant.x][en_passant.y][14]
            return current ^ GameState.Zobrist.black_to_move

        @staticmethod
        def index_of(piece: str) -> int:
            chars = "TPNBRQKtpnbrqk*"
            return chars.find(piece)

    rookDirections = [Position(0, 1), Position(1, 0), Position(-1, 0), Position(0, -1)]
    bishopDirections = [Position(1, 1), Position(1, -1), Position(-1, 1), Position(-1, -1)]
    queenDirections = rookDirections + bishopDirections
    knightMoves = [Position(2, 1), Position(1, 2), Position(-1, 2), Position(-2, 1), 
                   Position(-2, -1), Position(-1, -2), Position(1, -2), Position(2, -1)]

    def __init__(self):
        self.board = [['.' for _ in range(5)] for _ in range(5)]
        self.whiteToMove = True
        self.enPassantTarget = Position.Null
        self.whiteKing = Position.Null
        self.blackKing = Position.Null
        GameState.Zobrist._initialize()

    def piece_is_movers(self, piece: str) -> bool:
        return piece.isupper() == self.whiteToMove

    def _current_player_is_in_check(self) -> bool:
        current_king = self.whiteKing if self.whiteToMove else self.blackKing
        return self._square_is_attacked(current_king, not self.whiteToMove)

    def is_drawn_by_only_kings(self) -> bool:
        pieces = 0
        for x in range(5):
            for y in range(5):
                p = self.board[x][y]
                if p != '.':
                    if p != 'K' and p != 'k': return False
                    pieces += 1
        return True

    def _move(self, move_from: Position, move_to: Position) -> MoveInfo:
        from_piece = self.board[move_from.x][move_from.y]
        to_piece = self.board[move_to.x][move_to.y]
        ep_piece = '.'
        promotion_piece = from_piece
        en_passant_taken = Position.Null
        previous_en_passant_target = self.enPassantTarget
        self.enPassantTarget = Position.Null

        is_promotion = False
        if from_piece in ('P', 'p', 'T', 't'):
            if move_to.y == 0 or move_to.y == 4:
                is_promotion = True
                promotion_piece = 'Q' if self.whiteToMove else 'q'
            elif abs(move_to.y - move_from.y) == 2:
                self.enPassantTarget = Position(move_from.x, (move_from.y + move_to.y) // 2)
            elif move_to == previous_en_passant_target:
                en_passant_taken = Position(previous_en_passant_target.x, previous_en_passant_target.y + (-1 if self.whiteToMove else 1))
                ep_piece = self.board[en_passant_taken.x][en_passant_taken.y]
                self.board[en_passant_taken.x][en_passant_taken.y] = '.'

        if from_piece in ('T', 't'):
            promotion_piece = 'P' if self.whiteToMove else 'p'
    
        self.board[move_to.x][move_to.y] = promotion_piece
        self.board[move_from.x][move_from.y] = '.'

        if from_piece == 'K': self.whiteKing = move_to
        elif from_piece == 'k': self.blackKing = move_to

        is_legal = not self._current_player_is_in_check()
        self.whiteToMove = not self.whiteToMove

        return MoveInfo(
            From=move_from, FromPiece=from_piece, To=move_to, ToPiece=to_piece,
            EP=en_passant_taken, EPPiece=ep_piece, PromotionPiece=promotion_piece,
            IsPromotion=is_promotion, IsLegal=is_legal,
            PreviousEnPassantTarget=previous_en_passant_target, NewEnPassantTarget=self.enPassantTarget
        )

    def undo_move(self, info: MoveInfo):
        self.board[info.From.x][info.From.y] = info.FromPiece
        self.board[info.To.x][info.To.y] = info.ToPiece
        if info.EP.is_valid():
            self.board[info.EP.x][info.EP.y] = info.EPPiece
        if info.FromPiece == 'K': self.whiteKing = info.From
        elif info.FromPiece == 'k': self.blackKing = info.From
        self.whiteToMove = not self.whiteToMove
        self.enPassantTarget = info.PreviousEnPassantTarget

    def _square_is_attacked(self, pos: Position, by_white: bool) -> bool:
        # Simplified attacker check (assuming correct mapping)
        suffix = "" if by_white else ".l" # Logic trick not needed if we check chars directly
        kn, bp, rp, qp, kp = ('N', 'B', 'R', 'Q', 'K') if by_white else ('n', 'b', 'r', 'q', 'k')
        pp, tp = ('P', 'T') if by_white else ('p', 't')

        for delta in GameState.knightMoves:
            ap = pos + delta
            if ap.is_valid():
                p = self.board[ap.x][ap.y]
                if p == kn or p == rp: return True

        if self._raytrace_attackers(pos, bp, qp, GameState.bishopDirections): return True
        if self._raytrace_attackers(pos, rp, qp, GameState.rookDirections): return True

        pdir = 1 if by_white else -1
        for delta in [Position(-1, -pdir), Position(1, -pdir)]:
            ap = pos + delta
            if ap.is_valid():
                p = self.board[ap.x][ap.y]
                if p == pp or p == tp: return True
        
        for delta in GameState.queenDirections:
            ap = pos + delta
            if ap.is_valid() and self.board[ap.x][ap.y] == kp: return True

        return False

    def _raytrace_attackers(self, pos: Position, p1: str, p2: str, vectors: Iterable[Position]) -> bool:
        for delta in vectors:
            cur = pos + delta
            while cur.is_valid():
                tp = self.board[cur.x][cur.y]
                if tp == '.':
                    cur += delta
                    continue
                elif tp == p1 or tp == p2: return True
                else: break
        return False
    
    def _get_moves(self) -> Iterable[PositionPair]:
        # Generate pseudo-legal moves
        for x in range(5):
            for y in range(5):
                piece = self.board[x][y]
                if piece == '.' or not self.piece_is_movers(piece): continue
                pos = Position(x, y)
                
                if piece in ('P', 'p'): yield from self._get_pawn_moves(pos, False)
                elif piece in ('T', 't'): yield from self._get_pawn_moves(pos, True)
                elif piece in ('N', 'n'): yield from self._apply_deltas(pos, GameState.knightMoves)
                elif piece in ('R', 'r'):
                    yield from self._raytrace_moves(pos, GameState.rookDirections)
                    yield from self._apply_deltas(pos, GameState.knightMoves)
                elif piece in ('B', 'b'): yield from self._raytrace_moves(pos, GameState.bishopDirections)
                elif piece in ('Q', 'q'): yield from self._raytrace_moves(pos, GameState.queenDirections)
                elif piece in ('K', 'k'): yield from self._apply_deltas(pos, GameState.queenDirections)

    def _get_pawn_moves(self, pos: Position, can_move_two: bool) -> Iterable[PositionPair]:
        direction = 1 if self.whiteToMove else -1
        f1 = Position(pos.x, pos.y + direction)
        if f1.is_valid() and self.board[f1.x][f1.y] == '.':
            yield PositionPair(pos, f1)
            f2 = Position(pos.x, pos.y + 2 * direction)
            if can_move_two and f2.is_valid() and self.board[f2.x][f2.y] == '.':
                yield PositionPair(pos, f2)
        
        for delta in [Position(-1, direction), Position(1, direction)]:
            ap = pos + delta
            if ap.is_valid():
                if self.board[ap.x][ap.y] != '.' and not self.piece_is_movers(self.board[ap.x][ap.y]):
                    yield PositionPair(pos, ap)
                elif ap == self.enPassantTarget:
                    yield PositionPair(pos, ap)

    def _raytrace_moves(self, pos: Position, moves: List[Position]) -> Iterable[PositionPair]:
        for delta in moves:
            cur = pos + delta
            while cur.is_valid():
                if self.board[cur.x][cur.y] == '.':
                    yield PositionPair(pos, cur)
                else:
                    if not self.piece_is_movers(self.board[cur.x][cur.y]):
                        yield PositionPair(pos, cur)
                    break
                cur += delta

    def _apply_deltas(self, pos: Position, deltas: List[Position]) -> Iterable[PositionPair]:
        for delta in deltas:
            to = pos + delta
            if to.is_valid() and (self.board[to.x][to.y] == '.' or not self.piece_is_movers(self.board[to.x][to.y])):
                yield PositionPair(pos, to)

# =============================================================================
# 3. MOVE GENERATOR & EVAL HELPERS
# =============================================================================

class MoveGenerator:
    @staticmethod
    def _is_forcing(game: GameState, move: PositionPair) -> bool:
        fp = game.board[move.From.x][move.From.y]
        tp = game.board[move.To.x][move.To.y]
        is_pawn = fp in ('P', 'p', 'T', 't')
        is_promo = is_pawn and (move.To.y == 0 or move.To.y == 4)
        is_ep = is_pawn and move.To == game.enPassantTarget
        return (tp != '.' or is_ep or is_promo)

    @staticmethod
    def _move_causes_check(game: GameState, move: PositionPair) -> bool:
        # Quick check for check
        promo_piece = game.board[move.From.x][move.From.y]
        if promo_piece in ('P', 'p', 'T', 't'):
            if move.To.y == 0 or move.To.y == 4:
                promo_piece = 'Q' if game.whiteToMove else 'q'
        
        opp_king = game.blackKing if game.whiteToMove else game.whiteKing
        if MoveGenerator._piece_attacks_square(game, promo_piece, move.To, opp_king): return True

        # Discovered check check
        delta = opp_king - move.From
        directions = []
        attacker_o = ''
        if delta.x == 0 or delta.y == 0:
            directions = GameState.rookDirections
            attacker_o = 'R' if game.whiteToMove else 'r'
        elif abs(delta.x) == abs(delta.y):
            directions = GameState.bishopDirections
            attacker_o = 'b' if game.whiteToMove else 'B'
        else: return False
        
        atk_q = 'Q' if game.whiteToMove else 'q'

        for d in directions:
            cur = move.From + d
            found_king = False
            while cur.is_valid():
                if cur == opp_king:
                    found_king = True
                    break
                if game.board[cur.x][cur.y] != '.': break
                cur += d
            
            if found_king:
                cur = move.From - d
                while cur.is_valid():
                    tp = game.board[cur.x][cur.y]
                    if tp != '.':
                        if tp == attacker_o or tp == atk_q: return True
                        break
                    cur -= d
        return False

    @staticmethod
    def _piece_attacks_square(game: GameState, piece: str, from_pos: Position, to_pos: Position) -> bool:
        delta = to_pos - from_pos
        if piece in ('P','p','T','t'):
            d = 1 if piece.isupper() else -1
            return delta == Position(-1, d) or delta == Position(1, d)
        elif piece in ('N','n'): return delta in GameState.knightMoves
        elif piece in ('R','r'):
            if delta.x != 0 and delta.y != 0: return False
            step = Position(0, 1 if delta.y>0 else -1) if delta.x==0 else Position(1 if delta.x>0 else -1, 0)
            cur = from_pos + step
            while cur != to_pos:
                if not cur.is_valid() or game.board[cur.x][cur.y] != '.': return False
                cur += step
            return True
        elif piece in ('B','b'):
            if abs(delta.x) != abs(delta.y): return False
            step = Position(1 if delta.x>0 else -1, 1 if delta.y>0 else -1)
            cur = from_pos + step
            while cur != to_pos:
                if not cur.is_valid() or game.board[cur.x][cur.y] != '.': return False
                cur += step
            return True
        elif piece in ('Q','q'):
            if delta.x==0 or delta.y==0: 
                return MoveGenerator._piece_attacks_square(game, 'R' if piece.isupper() else 'r', from_pos, to_pos)
            return MoveGenerator._piece_attacks_square(game, 'B' if piece.isupper() else 'b', from_pos, to_pos)
        elif piece in ('K','k'):
            return max(abs(delta.x), abs(delta.y)) == 1
        return False

# =============================================================================
# 4. ANALYSIS ENGINE (Instance Based, No Timeouts, Interrupts on Board Change)
# =============================================================================

class SearchResetException(Exception):
    """Thrown when the board changes in the main thread."""
    pass

class AnalysisEngine:
    class MemoEntryType(enum.Enum):
        Exact = 0; LowerBound = 1; UpperBound = 2

    @dataclass(frozen=True)
    class MemoEntry:
        Value: int
        Depth: int
        Type: 'AnalysisEngine.MemoEntryType'
        Move: ReducedMoveInfo
        Valid: bool = True
    
    MemoEntry.Default = MemoEntry(0, 0, MemoEntryType.Exact, ReducedMoveInfo(Position.Null, Position.Null), False)

    # PST Tables (Copied from Agent)
    pst_pawn = [[0,0,0,0,0],[5,10,10,10,5],[20,30,40,30,20],[50,70,90,70,50],[0,0,0,0,0]]
    pst_knight = [[-20,-10,-10,-10,-20],[-10,5,10,5,-10],[-10,15,30,15,-10],[-10,5,10,5,-10],[-20,-10,-10,-10,-20]]
    pst_bishop = [[-10,-5,-10,-5,-10],[-5,5,5,5,-5],[-10,10,20,10,-10],[-5,5,5,5,-5],[-10,-5,-10,-5,-10]]
    pst_right = [[-15,-5,-5,-5,-15],[-5,5,10,5,-5],[-5,10,20,10,-5],[-5,5,10,5,-5],[-15,-5,-5,-5,-15]]
    pst_queen = [[-5,-5,-5,-5,-5],[-5,5,5,5,-5],[-5,10,15,10,-5],[-5,5,5,5,-5],[-5,-5,-5,-5,-5]]
    pst_king_mg = [[20,30,10,30,20],[10,0,-20,0,10],[-20,-30,-50,-30,-20],[-30,-40,-50,-40,-30],[-50,-50,-50,-50,-50]]
    pst_king_eg = [[-20,-10,-10,-10,-20],[-10,10,20,10,-10],[-10,20,40,20,-10],[-10,10,20,10,-10],[-20,-10,-10,-10,-20]]

    def __init__(self, evaluator_instance):
        self.parent = evaluator_instance
        self.memo = {}
        self.killer_moves = [[None, None] for _ in range(64)]
        self.history = [[[[0]*5 for _ in range(5)] for _ in range(5)] for _ in range(5)]
        self.repetition_table = {}
        self.current_root_board_obj = None # The actual board object we are analyzing

    def check_interrupt(self):
        # The core change: Interrupt if the target board pointer changes
        if self.parent.target_board is not self.current_root_board_obj:
            raise SearchResetException()

    def _piece_to_points(self, p):
        if p in 'PpTt': return 100
        if p in 'NnBb': return 300
        if p in 'Rr': return 600
        if p in 'Qq': return 900
        return 0

    def _position_to_points(self, pos, p, is_eg):
        x, y = pos.x, pos.y if p.isupper() else 4 - pos.y
        if p in 'PpTt': return self.pst_pawn[y][x]
        if p in 'Nn': return self.pst_knight[y][x]
        if p in 'Bb': return self.pst_bishop[y][x]
        if p in 'Rr': return self.pst_right[y][x]
        if p in 'Qq': return self.pst_queen[y][x]
        if p in 'Kk': return self.pst_king_eg[y][x] if is_eg else self.pst_king_mg[y][x]
        return 0

    def _heuristic(self, game):
        is_eg = True
        for x in range(5):
            for y in range(5):
                p = game.board[x][y]
                if p == ('q' if game.whiteToMove else 'Q') or p == ('r' if game.whiteToMove else 'R'):
                    is_eg = False
                    break
        
        score = 0
        pieces = 0
        for x in range(5):
            for y in range(5):
                p = game.board[x][y]
                if p == '.': continue
                pieces += 1
                val = self._piece_to_points(p) + self._position_to_points(Position(x,y), p, is_eg)
                if game.piece_is_movers(p): score += val
                else: score -= val
        
        if score > 0: score -= pieces
        elif score < 0: score += pieces
        return score

    def generate_moves(self, game, memo_entry, ply):
        # Simplified replication of Agent.generate_moves buckets
        k1 = self.killer_moves[ply][0] if ply < 64 else None
        k2 = self.killer_moves[ply][1] if ply < 64 else None
        
        moves = []
        for pair in game._get_moves():
            rm = ReducedMoveInfo(pair.From, pair.To)
            if memo_entry.Valid and rm == memo_entry.Move:
                yield pair, MoveGenerator._move_causes_check(game, pair) # Yield PV first
                continue
            
            fp = game.board[pair.From.x][pair.From.y]
            tp = game.board[pair.To.x][pair.To.y]
            is_promo = fp in 'PpTt' and (pair.To.y == 0 or pair.To.y == 4)
            
            score = 0
            is_check = None

            if is_promo:
                score = 8000000
            elif tp != '.': # Capture
                vic = self._piece_to_points(tp)
                agg = self._piece_to_points(fp)
                score = 7000000 + (10*vic - agg)
            elif rm == k1: score = 2000000
            elif rm == k2: score = 1000000
            else:
                score = self.history[pair.From.x][pair.From.y][pair.To.x][pair.To.y]
            
            moves.append((score, pair))
        
        moves.sort(key=lambda x: x[0], reverse=True)
        for _, pair in moves:
            yield pair, MoveGenerator._move_causes_check(game, pair)

    def generate_q_moves(self, game, memo_entry):
        moves = []
        for pair in game._get_moves():
            if not MoveGenerator._is_forcing(game, pair): continue
            fp = game.board[pair.From.x][pair.From.y]
            tp = game.board[pair.To.x][pair.To.y]
            
            score = 0
            if fp in 'PpTt' and (pair.To.y in (0,4)): score = 8000000
            else:
                vic = self._piece_to_points(tp)
                agg = self._piece_to_points(fp)
                score = 7000000 + (10*vic - agg)
            moves.append((score, pair))
        
        moves.sort(key=lambda x: x[0], reverse=True)
        for _, pair in moves: yield pair

    def quiescence(self, game, alpha, beta, ply, hash_val, q_depth):
        self.check_interrupt()

        if self.repetition_table.get(hash_val, 0) >= 2: return 0

        memo = self.memo.get(hash_val)
        if memo and memo.Depth >= 0: # QSearch uses depth 0 logic
            if memo.Type == self.MemoEntryType.Exact: return memo.Value
            if memo.Type == self.MemoEntryType.LowerBound: alpha = max(alpha, memo.Value)
            if memo.Type == self.MemoEntryType.UpperBound: beta = min(beta, memo.Value)
            if alpha >= beta: return memo.Value

        if q_depth == 0: return self._heuristic(game)

        stand_pat = self._heuristic(game)
        if stand_pat >= beta: return beta
        alpha = max(alpha, stand_pat)

        best_move = ReducedMoveInfo(Position.Null, Position.Null)
        max_val = stand_pat
        
        moves = self.generate_q_moves(game, memo if memo else self.MemoEntry.Default)
        
        for pair in moves:
            info = game._move(pair.From, pair.To)
            if not info.IsLegal:
                game.undo_move(info)
                continue
            
            new_hash = GameState.Zobrist.update_hash(hash_val, info)
            val = -self.quiescence(game, -beta, -alpha, ply+1, new_hash, q_depth-1)
            game.undo_move(info)

            if val > max_val:
                max_val = val
                best_move = info.to_reduced_move_info()
            
            alpha = max(alpha, val)
            if alpha >= beta: break
        
        tt_type = self.MemoEntryType.Exact
        if max_val >= beta: tt_type = self.MemoEntryType.LowerBound
        elif max_val <= alpha: tt_type = self.MemoEntryType.UpperBound
        
        if not memo or memo.Depth <= 0:
            self.memo[hash_val] = self.MemoEntry(max_val, 0, tt_type, best_move)
        
        return max_val

    def negamax(self, game, alpha, beta, depth, ply, hash_val, in_check=False):
        self.check_interrupt()

        if self.repetition_table.get(hash_val, 0) >= 2: return 0
        if depth <= 0: return self.quiescence(game, alpha, beta, ply, hash_val, 8)

        memo = self.memo.get(hash_val)
        if memo and memo.Depth >= depth:
            if memo.Type == self.MemoEntryType.Exact: return memo.Value
            if memo.Type == self.MemoEntryType.LowerBound: alpha = max(alpha, memo.Value)
            if memo.Type == self.MemoEntryType.UpperBound: beta = min(beta, memo.Value)
            if alpha >= beta: return memo.Value

        if game.is_drawn_by_only_kings(): return 0

        # Futility & Null Move Pruning omitted for brevity/stability in infinite analysis context, 
        # but you can add them back if desired. Keeping it solid for now.

        moves = self.generate_moves(game, memo if memo else self.MemoEntry.Default, ply)
        
        max_val = -1_000_000_000
        best_move = MoveInfo.Default
        orig_alpha = alpha
        move_cnt = 0
        
        for pair, is_chk in moves:
            info = game._move(pair.From, pair.To)
            if not info.IsLegal:
                game.undo_move(info)
                continue
            
            move_cnt += 1
            new_hash = GameState.Zobrist.update_hash(hash_val, info)
            self.repetition_table[new_hash] = self.repetition_table.get(new_hash, 0) + 1
            
            if is_chk is None: is_chk = MoveGenerator._move_causes_check(game, pair)

            val = 0
            if move_cnt == 1:
                val = -self.negamax(game, -beta, -alpha, depth-1, ply+1, new_hash, is_chk)
            else:
                # PVS / LMR
                reduction = 0
                if depth >= 3 and not is_chk and (info.ToPiece=='.' and not info.IsPromotion):
                    reduction = int(0.5 + math.log(depth)*math.log(move_cnt)/2.0)
                    reduction = min(reduction, depth-2)
                
                val = -self.negamax(game, -(alpha+1), -alpha, depth-1-reduction, ply+1, new_hash, is_chk)
                if val > alpha and reduction > 0:
                    val = -self.negamax(game, -beta, -alpha, depth-1, ply+1, new_hash, is_chk)
                elif val > alpha and val < beta:
                    val = -self.negamax(game, -beta, -alpha, depth-1, ply+1, new_hash, is_chk)

            self.repetition_table[new_hash] -= 1
            game.undo_move(info)

            if val > max_val:
                max_val = val
                best_move = info
                if info.ToPiece == '.' and not info.IsPromotion:
                     self.history[pair.From.x][pair.From.y][pair.To.x][pair.To.y] += depth*depth
            
            alpha = max(alpha, val)
            if alpha >= beta:
                if info.ToPiece == '.' and not info.IsPromotion:
                    rm = info.to_reduced_move_info()
                    if rm != self.killer_moves[ply][0]:
                        self.killer_moves[ply][1] = self.killer_moves[ply][0]
                        self.killer_moves[ply][0] = rm
                break
        
        if move_cnt == 0: return -(10000 + depth)

        tt_type = self.MemoEntryType.Exact
        if max_val <= orig_alpha: tt_type = self.MemoEntryType.UpperBound
        elif max_val >= beta: tt_type = self.MemoEntryType.LowerBound
        
        self.memo[hash_val] = self.MemoEntry(max_val, depth, tt_type, best_move.to_reduced_move_info())
        return max_val

# =============================================================================
# 5. BACKGROUND EVALUATOR WRAPPER
# =============================================================================

class BackgroundEvaluator:
    def __init__(self):
        self.target_board = None
        self.stop_signal = False
        self.lock = threading.Lock()
        
        # Results
        self.current_score = 0.0
        self.is_mate = False
        self.mate_in = 0
        
        self.engine = AnalysisEngine(self)
        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.thread.start()

    def set_board(self, board):
        # Atomic update of the pointer
        with self.lock:
            # We clone deeply to ensure the main thread can't mutate the object 
            # while the worker is setting it up, but strictly speaking,
            # we just need a stable reference. 
            self.target_board = board.clone() 

    def get_evaluation(self):
        with self.lock:
            return self.current_score, self.is_mate, self.mate_in

    def stop(self):
        self.stop_signal = True

    def worker(self):
        while not self.stop_signal:
            
            # 1. Get Job
            my_board_obj = None
            with self.lock:
                if self.target_board:
                    my_board_obj = self.target_board
            
            if not my_board_obj:
                time.sleep(0.1)
                continue

            # 2. Setup Analysis Engine for this specific board
            self.engine.current_root_board_obj = my_board_obj
            self.engine.memo.clear()
            self.engine.repetition_table.clear()
            self.engine.history = [[[[0]*5 for _ in range(5)] for _ in range(5)] for _ in range(5)]

            # Build GameState
            state = GameState()
            
            # Repopulate State
            # (Assuming standard imports are not available, using raw strings for simplicity)
            # Reconstruct board from my_board_obj
            # Note: We must be careful mapping CM board to Eval board.
            
            # Find EP Target logic:
            # We have to deduce it because cloning might lose transient EP state 
            # if not stored explicitly. But standard Board clone keeps it.
            
            ep_pos = Position.Null
            
            # Helper to map CM Piece to char
            def get_char(p):
                n = p.name
                if n=='Knight': c='N'
                elif n=='Pawn' and p._moved_turns_ago == -1: c='T'
                else: c=n[0]
                return c if p.player.name=='white' else c.lower()

            for x in range(5):
                for y in range(5):
                    # Logic Flip: CM is 0=Bottom, Eval is 0=Bottom?
                    # Agent code uses: Position(cm_pos.x, 4 - cm_pos.y)
                    # Let's stick to that convention
                    row = 4 - y 
                    col = x
                    
                    try:
                        sq = my_board_obj._squares[row][col]
                        if sq.piece:
                            char = get_char(sq.piece)
                            state.board[x][y] = char
                            if char == 'K': state.whiteKing = Position(x,y)
                            elif char == 'k': state.blackKing = Position(x,y)
                            
                            # EP Check
                            if char in 'Pp' and sq.piece.name=='Pawn':
                                # Check if just moved 2 squares
                                if sq.piece._moved_turns_ago == 0:
                                    # This piece just moved. Was it a double move?
                                    prev = sq.piece._last_position
                                    if prev:
                                        curr_y = sq.position.y # CM Y
                                        prev_y = prev.y
                                        if abs(curr_y - prev_y) == 2:
                                            # EP Target is middle
                                            mid_y = (curr_y + prev_y) // 2
                                            # Convert to Agent Coord
                                            ep_pos = Position(x, 4 - mid_y)
                    except: pass
            
            state.enPassantTarget = ep_pos
            state.whiteToMove = (my_board_obj.current_player.name == 'white')
            
            root_hash = GameState.Zobrist.compute_hash(state)
            self.engine.repetition_table[root_hash] = 1

            # 3. Infinite Deepening Loop
            try:
                for depth in range(1, 100): # Effectively infinite
                    # PVS / Negamax Call
                    # Alpha/Beta window
                    alpha = -1000000
                    beta = 1000000
                    
                    val = self.engine.negamax(state, alpha, beta, depth, 0, root_hash)
                    
                    print(f"== BG analysis ==")
                    print(f"Depth {depth} Eval: {val} (Hash Entries: {len(self.engine.memo)})")

                    # Update UI
                    with self.lock:
                        final_score = val if state.whiteToMove else -val
                        
                        if abs(final_score) > 9000:
                            self.is_mate = True
                            dist = 10000 + depth - abs(final_score)
                            # If final_score positive -> White is mating -> mate_in positive
                            self.mate_in = dist if final_score > 0 else -dist
                            self.current_score = final_score
                        else:
                            self.is_mate = False
                            self.mate_in = 0
                            self.current_score = final_score / 100.0
                    
                    # No sleep! Go deeper immediately!
            
            except SearchResetException:
                # Board changed! Loop back to "Get Job" immediately
                pass
            except Exception as e:
                print(f"Eval Error: {e}")
                time.sleep(1) # Safety backoff