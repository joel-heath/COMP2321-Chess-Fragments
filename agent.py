from extension.board_utils import take_notes
# from extension.board_utils import list_legal_moves_for, copy_piece_move, take_notes
# from extension.board_rules import only_2kings, cannot_move
from chessmaker.chess.base import Board as CM_Board, Player as CM_Player, Piece as CM_Piece, MoveOption as CM_MoveOption, Position as CM_Position, Square as CM_Square
# from chessmaker.chess.pieces import King as CM_King
from typing import Iterable

type CM_Move = tuple[CM_Piece, CM_MoveOption]


### == Below be the C# agent translated into Python == ###
### == Beware of befuddling code == ###
### == Agent function at bottom of file == ###

import math
import enum
import random
import time
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, NamedTuple
from functools import total_ordering

# =============================================================================
# Position.cs
# =============================================================================
@total_ordering
class Position:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    @staticmethod
    def _to_char(index: int) -> str:
        return chr(ord('a') + index)

    def __str__(self) -> str:
        return f"{self._to_char(self.x)}{self.y + 1}"

    def __repr__(self) -> str:
        return f"Position(x={self.x}, y={self.y})"

    def __add__(self, other: 'Position') -> 'Position':
        return Position(self.x + other.x, self.y + other.y)

    def __sub__(self, other: 'Position') -> 'Position':
        return Position(self.x - other.x, self.y - other.y)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Position):
            return (self.x == other.x and self.y == other.y) or (self.is_null() and other.is_null())
        if isinstance(other, str):
            return str(self) == other
        if isinstance(other, tuple):
            return (self.x, self.y) == other
        return False
    
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Position):
            return NotImplemented
        return (self.x, self.y) < (other.x, other.y)

    def __hash__(self) -> int:
        return hash((self.x, self.y))

    def is_valid(self) -> bool:
        return 0 <= self.x < 5 and 0 <= self.y < 5

    def is_null(self) -> bool:
        return not self.is_valid()

Position.Null = Position(-1, -1)


# =============================================================================
# PositionPair.cs
# =============================================================================
class PositionPair(NamedTuple):
    From: Position
    To: Position


# =============================================================================
# MoveInfo.cs
# =============================================================================
class ReducedMoveInfo(NamedTuple):
    From: Position
    To: Position

@dataclass(frozen=True)
class MoveInfo:
    From: Position
    FromPiece: str
    To: Position
    ToPiece: str
    PromotionPiece: str  # What FromPiece becomes after move, unchanged except for pawn promotion to queen or double jumping pawn to normal pawn
    EP: Position  # The piece position captured by en passant
    EPPiece: str  # The piece captured by en passant
    IsPromotion: bool
    IsLegal: bool
    PreviousEnPassantTarget: Position
    NewEnPassantTarget: Position

    def to_reduced_move_info(self) -> ReducedMoveInfo:
        return ReducedMoveInfo(self.From, self.To)

# Used to represent default(MoveInfo)
MoveInfo.Default = MoveInfo(
    From=Position.Null,
    FromPiece='.',
    To=Position.Null,
    ToPiece='.',
    EP=Position.Null,
    EPPiece='.',
    PromotionPiece='.',
    IsPromotion=False,
    IsLegal=False,
    PreviousEnPassantTarget=Position.Null,
    NewEnPassantTarget=Position.Null
)


# =============================================================================
# Board.cs
# =============================================================================
class Board:
    # lowercase is black, uppercase is white
    # [0, 0] is a1, [1, 0] is b1, ..., [4, 4] is e5
    # to print in order, read the rows upside down. cols are correct.

    def __init__(self, setup: Optional[str] = None):
        self.board: List[List[str]] = [['.' for _ in range(5)] for _ in range(5)]
        self._initialize_board(setup)

    def _initialize_board(self, string_board: Optional[str] = None):
        if string_board is None:
            string_board = """
n q k b r
p p p p p
. . . . .
P P P P P
R B K Q N
"""
        
        rows = string_board.strip().split('\n')
        for r in range(5):
            cols = rows[5 - r - 1].strip().split(' ')
            for c in range(5):
                self.board[c][r] = cols[c][0]

    def __getitem__(self, key) -> str:
        if isinstance(key, Position):
            return self.board[key.x][key.y]
        elif isinstance(key, tuple) and len(key) == 2:
            return self.board[key[0]][key[1]]
        raise TypeError("Index must be a Position or (x, y) tuple")

    def __setitem__(self, key, value: str):
        if isinstance(key, Position):
            self.board[key.x][key.y] = value
        elif isinstance(key, tuple) and len(key) == 2:
            self.board[key[0]][key[1]] = value
        else:
            raise TypeError("Index must be a Position or (x, y) tuple")

    def __str__(self) -> str:
        sb = []
        for r in range(4, -1, -1):
            for c in range(5):
                sb.append(self.board[c][r])
                sb.append(' ')
            sb.append('\n')
        return "".join(sb)

    def print_board(self):
        take_notes(str(self))


# =============================================================================
# DrawDetector.cs
# =============================================================================
class DrawDetector:
    positions: Dict[int, int] = {}

    @staticmethod
    def moves_made() -> int:
        return len(DrawDetector.positions)

    @staticmethod
    def do(hash_val: int):
        DrawDetector.positions[hash_val] = DrawDetector.positions.get(hash_val, 0) + 1

    @staticmethod
    def undo(hash_val: int):
        DrawDetector.positions[hash_val] -= 1
        if DrawDetector.positions[hash_val] == 0:
            del DrawDetector.positions[hash_val]

    @staticmethod
    def is_drawn(hash_val: int) -> bool:
        return DrawDetector.positions.get(hash_val, 0) >= 5

    @staticmethod
    def check_for_draw() -> bool:
        return any(v >= 5 for v in DrawDetector.positions.values())


# =============================================================================
# GameState.cs (and Zobrist.cs)
# =============================================================================
class GameState:
    
    # --- Zobrist.cs nested class ---
    class Zobrist:
        _random = random.Random(0)
        zobrist_table: List[List[List[int]]] = []
        black_to_move: int = 0
        
        @staticmethod
        def _random_ulong() -> int:
            # Return a 64-bit integer
            return GameState.Zobrist._random.getrandbits(64)

        @staticmethod
        def _initialize():
            GameState.Zobrist.black_to_move = GameState.Zobrist._random_ulong()
            GameState.Zobrist.zobrist_table = [[[GameState.Zobrist._random_ulong() for _ in range(15)] for _ in range(5)] for _ in range(5)]
        
        @staticmethod
        def compute_hash(game: 'GameState') -> int:
            h = 0

            for i in range(5):
                for j in range(5):
                    piece = game.board[i, j]
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
            from_index = GameState.Zobrist.index_of(move.FromPiece)
            to_index = GameState.Zobrist.index_of(move.ToPiece)
            ep_index = GameState.Zobrist.index_of(move.EPPiece)
            promo_index = GameState.Zobrist.index_of(move.PromotionPiece)

            # XOR out the piece from its old square
            current ^= GameState.Zobrist.zobrist_table[move.From.x][move.From.y][from_index]

            # XOR out the captured piece (if any)
            if to_index != -1:
                current ^= GameState.Zobrist.zobrist_table[move.To.x][move.To.y][to_index]

            # XOR out the en passant captured pawn (if any)
            if move.EPPiece != '.':
                current ^= GameState.Zobrist.zobrist_table[move.EP.x][move.EP.y][ep_index]

            # XOR in the piece at its new square
            current ^= GameState.Zobrist.zobrist_table[move.To.x][move.To.y][promo_index]

            # STATE CHANGES

            # XOR the side to move
            current ^= GameState.Zobrist.black_to_move

            # XOR out the old en passant square (if any)
            if move.PreviousEnPassantTarget.is_valid():
                current ^= GameState.Zobrist.zobrist_table[move.PreviousEnPassantTarget.x][move.PreviousEnPassantTarget.y][14]

            # XOR in the new en passant square (if any)
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
            if piece == 'T': # pawn that can move two squares
                return 0
            if piece == 'P':
                return 1
            if piece == 'N':
                return 2
            if piece == 'B':
                return 3
            if piece == 'R':
                return 4
            if piece == 'Q':
                return 5
            if piece == 'K':
                return 6
            if piece == 't':
                return 7
            if piece == 'p':
                return 8
            if piece == 'n':
                return 9
            if piece == 'b':
                return 10
            if piece == 'r':
                return 11
            if piece == 'q':
                return 12
            if piece == 'k':
                return 13
            if piece == '*':
                return 14  # en passant marker
            return -1

    # --- End of Zobrist ---

    rookDirections = [Position(0, 1), Position(1, 0), Position(-1, 0), Position(0, -1)]
    bishopDirections = [Position(1, 1), Position(1, -1), Position(-1, 1), Position(-1, -1)]
    queenDirections = rookDirections + bishopDirections
    knightMoves = [Position(2, 1), Position(1, 2), Position(-1, 2), Position(-2, 1), 
                   Position(-2, -1), Position(-1, -2), Position(1, -2), Position(2, -1)]

    enPassantTarget: Position
    board: Board
    whiteToMove: bool
    whiteKing: Position
    blackKing: Position

    def __init__(self, setup: Optional[str] = None, whiteToMove: bool = True):
        self.whiteToMove = whiteToMove
        self.board = Board(setup)
        self.enPassantTarget = Position.Null

        if not GameState.Zobrist.zobrist_table:
            GameState.Zobrist._initialize()

        for piece, position in self.get_positions():
            if piece == 'K':
                self.whiteKing = position
            elif piece == 'k':
                self.blackKing = position

    def piece_is_movers(self, piece: str) -> bool:
        return piece.isupper() == self.whiteToMove

    def _opponent_is_in_check(self) -> bool:
        opponent_king = self.blackKing if self.whiteToMove else self.whiteKing
        return self._square_is_attacked(opponent_king, self.whiteToMove)
    
    def _current_player_is_in_check(self) -> bool:
        current_king = self.whiteKing if self.whiteToMove else self.blackKing
        return self._square_is_attacked(current_king, not self.whiteToMove)
    
    def current_player_is_mated(self) -> bool:
        return not any(self.get_legal_moves(limit_depth=True))

    def is_drawn_by_only_kings(self) -> bool:
        return all(p == '.' or p == 'K' or p == 'k' for p, _ in self.get_positions())

    def _move(self, move_from: Position, move_to: Position) -> MoveInfo:
        from_piece = self.board[move_from]
        to_piece = self.board[move_to]
        ep_piece = '.'
        promotion_piece = from_piece
        en_passant_taken = Position.Null
        previous_en_passant_target = self.enPassantTarget
        self.enPassantTarget = Position.Null

        is_promotion = False
        if from_piece == 'P' or from_piece == 'p' or from_piece == 'T' or from_piece == 't':
            if move_to.y == 0 or move_to.y == 4:
                is_promotion = True
                promotion_piece = 'Q' if self.whiteToMove else 'q'
            elif abs(move_to.y - move_from.y) == 2:
                self.enPassantTarget = Position(move_from.x, (move_from.y + move_to.y) // 2)
            elif move_to == previous_en_passant_target:
                en_passant_taken = Position(previous_en_passant_target.x, previous_en_passant_target.y + (-1 if self.whiteToMove else 1))
                ep_piece = self.board[en_passant_taken]
                self.board[en_passant_taken] = '.'

        if from_piece == 'T' or from_piece == 't':
            promotion_piece = 'P' if self.whiteToMove else 'p'
    
        self.board[move_to] = promotion_piece
        self.board[move_from] = '.'

        if from_piece == 'K':
            self.whiteKing = move_to
        elif from_piece == 'k':
            self.blackKing = move_to

        # check legality first
        is_legal = not self._current_player_is_in_check()

        # finally switch sides for next move
        self.whiteToMove = not self.whiteToMove

        return MoveInfo(
            From=move_from,
            FromPiece=from_piece,
            To=move_to,
            ToPiece=to_piece,
            EP=en_passant_taken,
            EPPiece=ep_piece,
            PromotionPiece=promotion_piece,
            IsPromotion=is_promotion,
            IsLegal=is_legal,
            PreviousEnPassantTarget=previous_en_passant_target,
            NewEnPassantTarget=self.enPassantTarget
        )

    def apply_move(self, info: MoveInfo):
        self.board[info.To] = info.PromotionPiece
        self.board[info.From] = '.'
        if info.EP.is_valid():
            self.board[info.EP] = '.'
        if info.FromPiece == 'K':
            self.whiteKing = info.To
        elif info.FromPiece == 'k':
            self.blackKing = info.To

        self.whiteToMove = not self.whiteToMove
        self.enPassantTarget = info.NewEnPassantTarget

    def undo_move(self, info: MoveInfo):
        self.board[info.From] = info.FromPiece
        self.board[info.To] = info.ToPiece

        if info.EP.is_valid():
            self.board[info.EP] = info.EPPiece
            # self.board[info.To] = '.' # This was commented out in C#, so kept here.

        if info.FromPiece == 'K':
            self.whiteKing = info.From
        elif info.FromPiece == 'k':
            self.blackKing = info.From

        self.whiteToMove = not self.whiteToMove
        self.enPassantTarget = info.PreviousEnPassantTarget

    def get_legal_moves(self, limit_depth: bool = False) -> Iterable[MoveInfo]:
        for move in self._get_moves():
            move_info = self._move(move.From, move.To, limit_depth)
            self.undo_move(move_info)  # _move modifies state, so we undo
            if move_info.IsLegal:
                yield move_info

    def _get_moves(self) -> Iterable[PositionPair]:
        pieces = self._get_pieces_for_current_player()
        for piece, pos in pieces:
            if piece == 'P' or piece == 'p':
                yield from self._get_pawn_moves(pos, False)
            elif piece == 'T' or piece == 't':
                yield from self._get_pawn_moves(pos, True)
            elif piece == 'N' or piece == 'n':
                yield from self._apply_deltas(pos, GameState.knightMoves)
            elif piece == 'R' or piece == 'r':
                yield from self._raytrace_moves(pos, GameState.rookDirections)
                yield from self._apply_deltas(pos, GameState.knightMoves)
            elif piece == 'B' or piece == 'b':
                yield from self._raytrace_moves(pos, GameState.bishopDirections)
            elif piece == 'Q' or piece == 'q':
                yield from self._raytrace_moves(pos, GameState.queenDirections)
            elif piece == 'K' or piece == 'k':
                yield from self._apply_deltas(pos, GameState.queenDirections)

    def _raytrace_attackers(self, pos: Position, piece1: str, piece2: str, vectors: Iterable[Position]) -> bool:
        for delta in vectors:
            current = pos + delta
            while current.is_valid():
                target_piece = self.board[current]
                if target_piece == '.':
                    current += delta
                    continue
                elif target_piece == piece1 or target_piece == piece2:
                    return True
                else:
                    break
        return False
    
    def _square_is_attacked(self, pos: Position, by_white: bool) -> bool:
        two_piece = 'T' if by_white else 't'
        pawn_piece = 'P' if by_white else 'p'
        knight_piece = 'N' if by_white else 'n'
        bishop_piece = 'B' if by_white else 'b'
        right_piece = 'R' if by_white else 'r'
        queen_piece = 'Q' if by_white else 'q'
        king_piece = 'K' if by_white else 'k'

        # Check knight attacks (and funny rook knight)
        for delta in GameState.knightMoves:
            attacker_pos = pos + delta
            if attacker_pos.is_valid() and (self.board[attacker_pos] == knight_piece or self.board[attacker_pos] == right_piece):
                return True

        # Check bishop attacks
        if self._raytrace_attackers(pos, bishop_piece, queen_piece, GameState.bishopDirections):
            return True

        # Check rook attacks
        if self._raytrace_attackers(pos, right_piece, queen_piece, GameState.rookDirections):
            return True

        # Check pawn attacks
        pawn_direction = 1 if by_white else -1
        attack_deltas = [Position(-1, -pawn_direction), Position(1, -pawn_direction)]
        for delta in attack_deltas:
            attacker_pos = pos + delta
            if attacker_pos.is_valid() and (self.board[attacker_pos] == pawn_piece or self.board[attacker_pos] == two_piece):
                return True

        # Check king attacks
        for delta in GameState.queenDirections:
            attacker_pos = pos + delta
            if attacker_pos.is_valid() and self.board[attacker_pos] == king_piece:
                return True

        return False

    def _get_pawn_moves(self, pos: Position, can_move_two: bool = False) -> Iterable[PositionPair]:
        direction = 1 if self.whiteToMove else -1
        
        forward_one = Position(pos.x, pos.y + direction)
        if forward_one.is_valid() and self.board[forward_one] == '.':
            yield PositionPair(pos, forward_one)
            forward_two = Position(pos.x, pos.y + 2 * direction)
            if can_move_two and forward_two.is_valid() and self.board[forward_two] == '.':
                yield PositionPair(pos, forward_two)
        
        attack_deltas = [Position(-1, direction), Position(1, direction)]
        for delta in attack_deltas:
            attack_pos = pos + delta
            if attack_pos.is_valid():
                target_piece = self.board[attack_pos]
                if target_piece != '.' and not self.piece_is_movers(target_piece):
                    yield PositionPair(pos, attack_pos)
                elif attack_pos == self.enPassantTarget:
                    yield PositionPair(pos, attack_pos)

    def _raytrace_moves(self, pos: Position, moves: List[Position]) -> Iterable[PositionPair]:
        for delta in moves:
            current = pos + delta
            while current.is_valid():
                target_piece = self.board[current]
                if target_piece == '.':
                    yield PositionPair(pos, current)
                else:
                    if not self.piece_is_movers(target_piece):
                        yield PositionPair(pos, current)
                    break
                current += delta

    def _apply_deltas(self, move_from: Position, to_deltas: List[Position]) -> Iterable[PositionPair]:
        for delta in to_deltas:
            move_to = move_from + delta
            if move_to.is_valid() and (self.board[move_to] == '.' or not self.piece_is_movers(self.board[move_to])):
                yield PositionPair(move_from, move_to)

    def _get_pieces_for_current_player(self) -> Iterable[Tuple[str, Position]]:
        return filter(lambda p: p[0] != '.' and self.piece_is_movers(p[0]), self.get_positions())

    def get_positions(self) -> Iterable[Tuple[str, Position]]:
        for c in range(5):
            for r in range(5):
                yield (self.board[c, r], Position(c, r))

    def print_board(self):
        self.board.print_board()

    def __str__(self) -> str:
        return str(self.board) + f"White to move: {self.whiteToMove}\nEn Passant Target: {str(self.enPassantTarget)}\n"


# =============================================================================
# MoveGenerator.cs (doesnt exist lol)
# =============================================================================

class MoveGenerator:
    @staticmethod
    def _is_forcing(game: GameState, move: PositionPair) -> bool:
        """Helper to check if a move is a capture or promotion."""
        from_piece = game.board[move.From]
        to_piece = game.board[move.To]
        
        is_pawn = from_piece in ('P', 'p', 'T', 't')
        is_promo = is_pawn and (move.To.y == 0 or move.To.y == 4)
        is_ep = is_pawn and move.To == game.enPassantTarget
        is_capture = to_piece != '.' or is_ep

        return is_promo or is_capture

    @staticmethod
    def generate_q_moves(game: GameState, memo_entry: 'Agent.MemoEntry') -> Iterable[PositionPair]:
        """
        Generates 'forcing' moves, prioritizing the TT 'hash_move' if it's
        a capture/promotion, then sorting the rest by MVV-LVA.
        """
        
        # --- Stage 1: Yield Hash Move ---
        # The hash move is the best move from a previous search.
        # If it's a forcing move, we MUST search it first.
        hash_move: Optional[ReducedMoveInfo] = None
        if memo_entry.Valid:
            hash_move_pair = PositionPair(memo_entry.Move.From, memo_entry.Move.To)
            if MoveGenerator._is_forcing(game, hash_move_pair):
                hash_move = memo_entry.Move
                yield hash_move_pair

        # --- Scoring Constants ---
        PROMO_SCORE = 8_000_000
        CAPTURE_BASE = 7_000_000
        
        q_moves: List[Tuple[int, PositionPair]] = []

        for move in game._get_moves():
            # Skip the hash move if we already yielded it
            if hash_move and move.From == hash_move.From and move.To == hash_move.To:
                continue
            
            from_piece = game.board[move.From]
            to_piece = game.board[move.To]
            
            is_promo = (from_piece in ('P', 'p', 'T', 't')) and (move.To.y == 0 or move.To.y == 4)
            is_ep = (from_piece in ('P', 'p', 'T', 't')) and move.To == game.enPassantTarget
            is_capture = to_piece != '.' or is_ep

            if is_promo:
                score = PROMO_SCORE
                if is_capture:
                    victim_piece = to_piece if not is_ep else ('p' if game.whiteToMove else 'P')
                    victim = Agent._piece_to_points(victim_piece)
                    score += (10 * victim)
                q_moves.append((score, move))
                
            elif is_capture:
                victim_piece = to_piece if not is_ep else ('p' if game.whiteToMove else 'P')
                aggressor = Agent._piece_to_points(from_piece)
                victim = Agent._piece_to_points(victim_piece)
                
                mvv_lva_score = 10 * victim - aggressor
                score = CAPTURE_BASE + mvv_lva_score
                q_moves.append((score, move))
            
            # All other moves (quiet moves) are ignored

        # --- Stage 2: Yield Sorted Moves ---
        q_moves.sort(reverse=True)
        for score, move in q_moves:
            yield move

    @staticmethod
    def generate_moves(game: GameState, memo_entry: 'Agent.MemoEntry', ply: int) -> Iterable[tuple[PositionPair, bool]]:
        # --- Stage 1: Hash Move ---
        # Yield the Transposition Table move immediately.
        if memo_entry.Valid:
            pair = PositionPair(memo_entry.Move.From, memo_entry.Move.To)
            yield pair, MoveGenerator._move_causes_check(game, pair)

        # --- Initialize Buckets for Stages ---
        promotions = []
        good_captures = []
        killers = []
        quiet_checks = []
        history_moves = []
        bad_captures = []
        
        # Get killer moves for this ply
        k1, k2 = None, None
        if ply < Agent.MAX_SEARCH_DEPTH:
            k1 = Agent.killer_moves[ply][0]
            k2 = Agent.killer_moves[ply][1]

        # --- Scoring Constants ---
        PROMO_CHECK_SCORE = 9_000_000
        PROMO_SCORE = 8_000_000
        GOOD_CAPTURE_BASE = 7_000_000
        HISTORY_BASE = 3_000_000
        BAD_CAPTURE_BASE = 1_000_000
        CHECK_BONUS = 10_000 # Bonus for checking captures

        # --- Stage 2: Single-pass Bucketing ---
        # Iterate all pseudo-legal moves ONCE and sort them into buckets
        for move in game._get_moves():
            reduced_move = ReducedMoveInfo(move.From, move.To)
            
            # Skip the hash move if we already yielded it
            if memo_entry.Valid and reduced_move == memo_entry.Move:
                continue

            from_piece = game.board[move.From]
            to_piece = game.board[move.To]
            is_promo = (from_piece in ('P', 'p', 'T', 't')) and (move.To.y == 0 or move.To.y == 4)

            # --- Bucket 2.1: Promotions ---
            if is_promo:
                # We only check for checks on high-priority moves to save time
                is_check = MoveGenerator._move_causes_check(game, move)
                score = PROMO_CHECK_SCORE if is_check else PROMO_SCORE
                promotions.append((score, move, is_check))
                continue

            # --- Bucket 2.2: Captures (MVV-LVA) ---
            if to_piece != '.':
                victim = Agent._piece_to_points(to_piece)
                aggressor = Agent._piece_to_points(from_piece)
                mvv_lva_score = 10 * victim - aggressor
                
                if victim > aggressor:
                    # Good captures
                    score = GOOD_CAPTURE_BASE + mvv_lva_score
                else:
                    # Bad captures
                    score = BAD_CAPTURE_BASE + mvv_lva_score
                
                is_check = None 
                # Check for checks only if it's a good capture (or a promotion)
                if victim > aggressor:
                    is_check = MoveGenerator._move_causes_check(game, move)
                    if is_check:
                        score += CHECK_BONUS

                if victim > aggressor:
                    good_captures.append((score, move, is_check))
                else:
                    bad_captures.append((score, move, is_check))
                continue

            # --- Bucket 2.3: Quiet Moves (Killers, History, Checks) ---
            # It must be a quiet move
            if reduced_move == k1:
                killers.append((2, move)) # Score 2 for 1st killer
            elif reduced_move == k2:
                killers.append((1, move)) # Score 1 for 2nd killer
            else:
                # Only check for checks *after* we've ruled out killers
                is_check = MoveGenerator._move_causes_check(game, move)
                if is_check:
                    quiet_checks.append(move)
                else:
                    # History Heuristic
                    score = Agent.history_table[move.From.x][move.From.y][move.To.x][move.To.y]
                    history_moves.append((score, move))

        # --- Stage 3: Yield from Buckets in Order ---
        
        # Yield Promotions (sorted by check/no-check)
        promotions.sort(reverse=True)
        for _, move, is_check in promotions:
            yield move, is_check
            
        # Yield Good Captures (sorted by MVV-LVA)
        good_captures.sort(reverse=True)
        for _, move, is_check in good_captures:
            yield move, is_check

        # Yield Killers (k1 then k2)
        killers.sort(reverse=True)
        for _, move in killers:
            yield move, None
            
        # Yield Quiet Checks
        for move in quiet_checks:
            yield move, True
            
        # Yield History Moves (sorted by history score)
        history_moves.sort(reverse=True)
        for _, move in history_moves:
            yield move, False
            
        # Yield Bad Captures (sorted by MVV-LVA)
        bad_captures.sort(reverse=True)
        for _, move, is_check in bad_captures:
            yield move, is_check

    @staticmethod
    def _move_causes_check(game: GameState, move: PositionPair) -> bool:
        # How to check for checking moves FAST?
        # after move see if moved piece now attacks opponent king
        # Check discovered checks:
        # we check the horizontal, vertical, diagonal lines from empty position the piece moved from
        # if king lies on none, no discovered check
        # if it does, iterate along to see if there is an attacker, emptiness, and king only

        promo_piece = game.board[move.From]
        if promo_piece == 'P' or promo_piece == 'p' or promo_piece == 'T' or promo_piece == 't':
            if move.To.y == 0 or move.To.y == 4:
                promo_piece = 'Q' if game.whiteToMove else 'q'

        # first, check if moved piece directly attacks opponent king
        opponent_king = game.blackKing if game.whiteToMove else game.whiteKing
        if MoveGenerator._piece_attacks_square(game, promo_piece, move.To, opponent_king):
            return True

        # next, check for discovered checks
        delta = opponent_king - move.From
        
        # check if delta is along rook, bishop, or queen lines
        directions = []
        attacker_q = 'Q' if game.whiteToMove else 'q'
        attacker_o = ''
        if delta.x == 0 or delta.y == 0:
            directions = GameState.rookDirections
            attacker_o = 'R' if game.whiteToMove else 'r'
        elif abs(delta.x) == abs(delta.y):
            directions = GameState.bishopDirections
            attacker_o = 'b' if game.whiteToMove else 'B'
        else:
            return False  # not along any line, no discovered check
        
        for direction in directions:
            current = move.From + direction
            found_king = False
            while current.is_valid():
                if current == opponent_king:
                    found_king = True
                    break
                target_piece = game.board[current]
                if target_piece != '.':
                    break
                current += direction
            if found_king:
                # now check if there is an attacker along this line
                current = move.From - direction
                while current.is_valid():
                    target_piece = game.board[current]
                    if target_piece != '.':
                        if target_piece == attacker_o or target_piece == attacker_q:
                            return True
                        break
                    current -= direction
        return False

        
    @staticmethod
    def _piece_attacks_square(game: GameState, piece: str, from_pos: Position, to_pos: Position) -> bool:
        delta = to_pos - from_pos

        if piece == 'P' or piece == 'p' or piece == 'T' or piece == 't':
            direction = 1 if piece.isupper() else -1
            if delta == Position(-1, direction) or delta == Position(1, direction):
                return True
            return False
        elif piece == 'N' or piece == 'n':
            return delta in GameState.knightMoves
        elif piece == 'R' or piece == 'r':
            if delta.x == 0:
                step = Position(0, 1 if delta.y > 0 else -1)
            elif delta.y == 0:
                step = Position(1 if delta.x > 0 else -1, 0)
            else:
                return False
            
            current = from_pos + step
            while current != to_pos:
                if not current.is_valid() or game.board[current] != '.':
                    return False
                current += step
            return True
        elif piece == 'B' or piece == 'b':
            if abs(delta.x) != abs(delta.y):
                return False
            step = Position(1 if delta.x > 0 else -1, 1 if delta.y > 0 else -1)
            current = from_pos + step
            while current != to_pos:
                if not current.is_valid() or game.board[current] != '.':
                    return False
                current += step
            return True
        elif piece == 'Q' or piece == 'q':
            # Combine rook and bishop logic
            if delta.x == 0 or delta.y == 0:
                return MoveGenerator._piece_attacks_square(game, 'R' if piece.isupper() else 'r', from_pos, to_pos)
            elif abs(delta.x) == abs(delta.y):
                return MoveGenerator._piece_attacks_square(game, 'B' if piece.isupper() else 'b', from_pos, to_pos)
            else:
                return False
        elif piece == 'K' or piece == 'k':
            return max(abs(delta.x), abs(delta.y)) == 1
        
        return False
    

    
    

# =============================================================================
# Agent.cs
# =============================================================================
class Agent:
    MAX_SEARCH_DEPTH = 64
    MAX_Q_DEPTH = 8
    
    # [ply][slot]
    killer_moves: List[List[Optional[ReducedMoveInfo]]] = [[None, None] for _ in range(MAX_SEARCH_DEPTH)]
    
    # [from_x][from_y][to_x][to_y]
    history_table: List[List[List[List[int]]]] = [[[[0 for _ in range(5)] for _ in range(5)] for _ in range(5)] for _ in range(5)]

    class MemoEntryType(enum.Enum):
        Exact = 0
        LowerBound = 1
        UpperBound = 2

    @dataclass(frozen=True)
    class MemoEntry:
        Value: int
        Depth: int
        Type: 'Agent.MemoEntryType'
        Move: ReducedMoveInfo
        Valid: bool = True

    # A default, invalid MemoEntry
    MemoEntry.Default = MemoEntry(0, 0, MemoEntryType.Exact, ReducedMoveInfo(Position.Null, Position.Null), False)

    memo = {}

    # -----------------------------------------------------------------------------
    # AI-GENERATED PIECE-SQUARE TABLES (White Perspective)
    # Values are additive centipawns (e.g., +10 means 0.1 pawn advantage)
    # -----------------------------------------------------------------------------

    # PAWN
    # Pawns start on Rank 1 or 2 (depending on setup). 
    # Rank 4 is promotion (value usually handled by engine promotion logic, so 0 here).
    # Ranks 2 and 3 are critical.
    pst_pawn = [
        [  0,   0,   0,   0,   0], # Rank 0 (Impossible)
        [  5,  10,  10,  10,   5], # Rank 1 (Start/Base)
        [ 20,  30,  40,  30,  20], # Rank 2 (Mid-field, good control)
        [ 50,  70,  90,  70,  50], # Rank 3 (Threatening promotion)
        [  0,   0,   0,   0,   0], # Rank 4 (Promoted)
    ]

    # KNIGHT
    # On 5x5, the center (2,2) hits 8 squares. 
    # Corners (0,0) hit only 2. Centralization is non-negotiable.
    pst_knight = [
        [-20, -10, -10, -10, -20], # Rank 0
        [-10,   5,  10,   5, -10], # Rank 1
        [-10,  15,  30,  15, -10], # Rank 2 (The golden square)
        [-10,   5,  10,   5, -10], # Rank 3
        [-20, -10, -10, -10, -20], # Rank 4
    ]

    # BISHOP
    # Long diagonals are short on 5x5. 
    # (2,2) is the only square that accesses two full length-5 diagonals.
    pst_bishop = [
        [-10,  -5, -10,  -5, -10], # Rank 0
        [ -5,   5,   5,   5,  -5], # Rank 1
        [-10,  10,  20,  10, -10], # Rank 2
        [ -5,   5,   5,   5,  -5], # Rank 3
        [-10,  -5, -10,  -5, -10], # Rank 4
    ]

    # QUEEN
    # High mobility. Should avoid corners where it can be trapped by the Knook.
    pst_queen = [
        [ -5,  -5,  -5,  -5,  -5], # Rank 0
        [ -5,   5,   5,   5,  -5], # Rank 1
        [ -5,  10,  15,  10,  -5], # Rank 2
        [ -5,   5,   5,   5,  -5], # Rank 3
        [ -5,  -5,  -5,  -5,  -5], # Rank 4
    ]

    # RIGHT
    # This piece is terrifying. It hits almost everything from everywhere.
    # The table rewards centralization slightly, but mostly punishes passive placement.
    # Even on the edge, it is strong, but center is best.
    pst_right = [
        [-15,  -5,  -5,  -5, -15], # Rank 0
        [ -5,   5,  10,   5,  -5], # Rank 1
        [ -5,  10,  20,  10,  -5], # Rank 2 (Center is King)
        [ -5,   5,  10,   5,  -5], # Rank 3
        [-15,  -5,  -5,  -5, -15], # Rank 4
    ]

    # KING (Middlegame)
    # Safety first. The board is small; corners are the only relative safe haven.
    # Center is death in the opening.
    pst_king_mg = [
        [ 20,  30,  10,  30,  20], # Rank 0 (Hide in B/D files)
        [ 10,   0, -20,   0,  10], # Rank 1
        [-20, -30, -50, -30, -20], # Rank 2 (Suicide zone)
        [-30, -40, -50, -40, -30], # Rank 3
        [-50, -50, -50, -50, -50], # Rank 4
    ]

    # KING (Endgame)
    # In the endgame, the King must become an active fighting piece.
    # Centralize to support pawns.
    pst_king_eg = [
        [-20, -10, -10, -10, -20], # Rank 0
        [-10,  10,  20,  10, -10], # Rank 1
        [-10,  20,  40,  20, -10], # Rank 2 (Maximum activity)
        [-10,  10,  20,  10, -10], # Rank 3
        [-20, -10, -10, -10, -20], # Rank 4
    ]

    @staticmethod
    def _piece_to_points(piece: str) -> int:
        if piece == 'P' or piece == 'p' or piece == 'T' or piece == 't':
            return 100
        if piece == 'N' or piece == 'n' or piece == 'B' or piece == 'b':
            return 300
        if piece == 'R' or piece == 'r':
            return 600
        if piece == 'Q' or piece == 'q':
            return 900
        return 0
    
    @staticmethod
    def _position_to_points(position: Position, piece: str, is_endgame: bool = False) -> int:
        x = position.x
        y = position.y if piece.isupper() else 4 - position.y
        if piece == 'P' or piece == 'T' or piece == 'p' or piece == 't':
            return Agent.pst_pawn[y][x]
        if piece == 'N' or piece == 'n':
            return Agent.pst_knight[y][x]
        if piece == 'B' or piece == 'b':
            return Agent.pst_bishop[y][x]
        if piece == 'R' or piece == 'r':
            return Agent.pst_right[y][x]
        if piece == 'Q' or piece == 'q':
            return Agent.pst_queen[y][x]
        if piece == 'K' or piece == 'k':
            if is_endgame:
                return Agent.pst_king_eg[y][x]
            else:
                return Agent.pst_king_mg[y][x]
        return 0
    
    
    # highest heuristic would be all pieces, all pawns promoted, all on the best positions
    # (9 + 3 + 3 + 6 + 0 + 9 * 5) * 100 + 90 * 10 = 7500
    # so checkmate will be scored at 10,000
    @staticmethod
    def _heuristic(game: GameState) -> int:
        # is endgame? game starts with 20 pieces and (9 + 3 + 3 + 6 + 0 + 5*1) = 2600 centipawns
        # total_material = 0
        # total_pieces = 0
        # for piece, pos in game.get_positions():
        #     total_material += Agent._piece_to_points(piece)
        #     if piece != '.':
        #         total_pieces += 1
        # is_endgame = total_material <= n or total_pieces <= m

        # but since the board is small, we need to be wary of the nukes: knooks and queens
        # if enemy knook or queen is on the board, we must hide our king
        is_endgame = True
        for piece, pos in game.get_positions():
            nukeQ = 'q' if game.whiteToMove else 'Q'
            nukeR = 'r' if game.whiteToMove else 'R'
            if piece == nukeQ or piece == nukeR:
                is_endgame = False
                break
        
        heuristic = 0
        total_pieces = 0
        for piece, pos in game.get_positions():
            total_pieces += 1
            is_for = game.piece_is_movers(piece)
            value = Agent._piece_to_points(piece) + Agent._position_to_points(pos, piece, is_endgame)
            heuristic += value if is_for else -value

        # finally, if we are winning, value simplification, as that will make it easier to convert to checkmate
        # if we are losing, value complicating the position to avoid losing quickly
        # each piece on the board is worth 1 centipawn, so all pieces on the board is worth 20 centipawns
        if heuristic > 0:
            heuristic -= total_pieces
        elif heuristic < 0:
            heuristic += total_pieces

        return heuristic

    @staticmethod
    def _negate(value: Optional[int]) -> Optional[int]:
        if value is not None:
            return -value
        return None

    @staticmethod
    def _quiescence(game: GameState, alpha: int, beta: int, ply: int, hash_val: int, q_depth: int, start_time: int, time_limit: int) -> Optional[int]:
        """
        Quiescence search with correct TT probing and storing at Depth = 0.
        Only evaluates forcing moves (captures, promotions).
        """
        if time.perf_counter() - start_time > time_limit:
            return None

        if DrawDetector.is_drawn(hash_val):
            return 0

        # === 1. TT Probe (as Depth 0) ===
        
        # THIS IS THE KEY: The "depth" for all q-search TT entries is 0.
        q_search_tt_depth = 0 
        
        memo_entry = Agent.memo.get(hash_val, None)
        
        # We probe for any entry with depth >= 0.
        # This will find other q-search results (depth 0)
        # AND deep main-search results (depth > 0), which is great.
        if memo_entry and memo_entry.Depth >= q_search_tt_depth:
            if memo_entry.Type == Agent.MemoEntryType.Exact:
                return memo_entry.Value
            elif memo_entry.Type == Agent.MemoEntryType.LowerBound:
                alpha = max(alpha, memo_entry.Value)
            elif memo_entry.Type == Agent.MemoEntryType.UpperBound:
                beta = min(beta, memo_entry.Value)
            if alpha >= beta:
                return memo_entry.Value

        if q_depth == 0:
            return Agent._heuristic(game)  # Max quiescence recursion reached

        # === 2. Stand-Pat Score ===
        stand_pat_score = Agent._heuristic(game)
        if stand_pat_score >= beta:
            # We are failing high. Store this as a Depth 0 LowerBound.
            # We don't need to check for overwrites, as storing a bound
            # that causes a cutoff is always good.
            Agent.memo[hash_val] = Agent.MemoEntry(stand_pat_score, q_search_tt_depth, Agent.MemoEntryType.LowerBound, ReducedMoveInfo(Position.Null, Position.Null))
            return beta
        
        alpha = max(alpha, stand_pat_score)
        
        max_val = stand_pat_score
        initial_alpha = alpha
        best_move_info = ReducedMoveInfo(Position.Null, Position.Null)

        # === 3. Generate and Search Forcing Moves ===
        valid_memo_entry = memo_entry if memo_entry else Agent.MemoEntry.Default
        moves = MoveGenerator.generate_q_moves(game, valid_memo_entry) # Still use TT move to order

        for position_pair in moves:
            info = game._move(position_pair.From, position_pair.To)
            if not info.IsLegal:
                game.undo_move(info)
                continue

            new_hash = GameState.Zobrist.update_hash(hash_val, info)
            DrawDetector.do(new_hash)

            value = Agent._quiescence(game, -beta, -alpha, ply + 1, new_hash, q_depth - 1, start_time, time_limit)
            value = Agent._negate(value)

            DrawDetector.undo(new_hash)
            game.undo_move(info)

            if value is None: # !! Timeout !!
                return None

            if value > max_val:
                max_val = value
                best_move_info = info.to_reduced_move_info()

            alpha = max(alpha, value)
            if alpha >= beta:
                break
        
        # === 4. TT Store (as Depth 0) ===
        memo_type = Agent.MemoEntryType.Exact
        if max_val <= initial_alpha:
            memo_type = Agent.MemoEntryType.UpperBound
        elif max_val >= beta:
            memo_type = Agent.MemoEntryType.LowerBound
        
        # CRITICAL: Only store this Depth 0 entry if it's not
        # overwriting a *deeper* main search entry.
        if not memo_entry or q_search_tt_depth >= memo_entry.Depth:
             Agent.memo[hash_val] = Agent.MemoEntry(max_val, q_search_tt_depth, memo_type, best_move_info)

        return max_val

    @staticmethod
    def _negamax(game: GameState, alpha: int, beta: int, depth: int, ply: int, hash_val: int, start_time: int, time_limit: int, in_check: bool = False) -> Optional[int]:
        if time.perf_counter() - start_time > time_limit:
            return None

        if DrawDetector.is_drawn(hash_val):
            return 0

        if depth == 0:
            return Agent._quiescence(game, alpha, beta, ply, hash_val, Agent.MAX_Q_DEPTH, start_time, time_limit)

        memo_entry = Agent.memo.get(hash_val, None)
        if memo_entry and memo_entry.Depth >= depth:
            if memo_entry.Type == Agent.MemoEntryType.Exact:
                return memo_entry.Value
            elif memo_entry.Type == Agent.MemoEntryType.LowerBound:
                alpha = max(alpha, memo_entry.Value)
            elif memo_entry.Type == Agent.MemoEntryType.UpperBound:
                beta = min(beta, memo_entry.Value)
            if alpha >= beta:
                return memo_entry.Value
        
        if game.is_drawn_by_only_kings():
            return 0

        # Futility pruning
        if (depth == 1 or depth == 2) and not in_check:
            static_eval = Agent._heuristic(game)
            futility_margin = 100 * (3 - depth) # 1 or 2 pawns
            if static_eval + futility_margin < alpha:
                return Agent._quiescence(game, alpha, beta, ply, hash_val, Agent.MAX_Q_DEPTH, start_time, time_limit)

        # Null Move Pruning
        # We use a zero-width window search after a null move to see if we can
        # cause a beta-cutoff. If we can, we assume the position is so good
        if depth >= 3 and not in_check:
            game.whiteToMove = not game.whiteToMove
            old_en_passant = game.enPassantTarget
            game.enPassantTarget = Position.Null
            new_hash = GameState.Zobrist.pass_turn(hash_val, old_en_passant)
            DrawDetector.do(new_hash)

            reduction = 2
            value = Agent._negamax(game, -beta, -beta + 1, depth - 1 - reduction, ply + 1, new_hash, start_time, time_limit, in_check)
            value = Agent._negate(value)

            game.whiteToMove = not game.whiteToMove
            game.enPassantTarget = old_en_passant
            DrawDetector.undo(new_hash)

            if value is None: # !! Timeout !!
                return None

            if value >= beta:
                return beta 

        max_val = -1_000_000_000 #-sys.maxsize
        best_move = MoveInfo.Default
        initial_alpha = alpha
        move_index = 0

        moves = MoveGenerator.generate_moves(game, memo_entry if memo_entry else Agent.MemoEntry.Default, ply)

        for poistion_pair, is_checking in moves:
            info = game._move(poistion_pair.From, poistion_pair.To)
            if not info.IsLegal:
                game.undo_move(info)
                continue

            if is_checking is None:
                # is_checking = game._current_player_is_in_check() # expensive
                is_checking = MoveGenerator._move_causes_check(game, poistion_pair) # faster
            
            # LMR
            move_index += 1

            new_hash = GameState.Zobrist.update_hash(hash_val, info)
            DrawDetector.do(new_hash)

            value = 0
                    
            if move_index == 1:
                # --- 1. Principal Variation (PV) Move ---
                # The first move (best_move from TT or history) is searched at full depth.
                value = Agent._negamax(game, -beta, -alpha, depth - 1, ply + 1, new_hash, start_time, time_limit, is_checking)
                value = Agent._negate(value)

            else:
                # --- 2. Non-PV Moves (LMR + Zero Window Search) ---

                reduction = 0
                is_quiet = (info.ToPiece == '.' and not info.IsPromotion)
                        
                if depth >= 3 and is_quiet and not is_checking:
                    reduction = int(0.5 + math.log(depth) * math.log(move_index) / 2.0)
                    reduction = max(0, reduction)
                    reduction = min(reduction, depth - 2) # Don't reduce into q-search

                new_depth = depth - 1 - reduction
                value = Agent._negamax(game, -(alpha + 1), -alpha, new_depth, ply + 1, new_hash, start_time, time_limit, is_checking)
                value = Agent._negate(value)

                if value is not None and value > alpha and reduction > 0:
                    value = Agent._negamax(game, -beta, -alpha, depth - 1, ply + 1, new_hash, start_time, time_limit, is_checking)
                    value = Agent._negate(value)

            DrawDetector.undo(new_hash)
            game.undo_move(info)

            if value is None: # !! Timeout !!
                return None

            if value > max_val:
                max_val = value
                best_move = info
                
                # Update history heuristic for good quiet moves
                if info.ToPiece == '.' and not info.EPPiece == '.' and not info.IsPromotion:
                    # Reward based on remaining depth squared
                    Agent.history_table[info.From.x][info.From.y][info.To.x][info.To.y] += depth * depth
            
            alpha = max(alpha, value)
            if alpha >= beta:
                # NEW: This quiet move caused a beta-cutoff, store it as a killer move
                if info.ToPiece == '.' and not info.IsPromotion:
                    reduced_move = info.to_reduced_move_info()
                    if reduced_move != Agent.killer_moves[ply][0]:
                        Agent.killer_moves[ply][1] = Agent.killer_moves[ply][0]
                        Agent.killer_moves[ply][0] = reduced_move
                break
        
        if move_index == 0: # best_move == MoveInfo.Default:
            return -(10_000 + depth) # no legal moves, you have been mated

        memo_type = Agent.MemoEntryType.Exact
        if max_val <= initial_alpha:
            memo_type = Agent.MemoEntryType.UpperBound
        elif max_val >= beta:
            memo_type = Agent.MemoEntryType.LowerBound
        
        if not memo_entry or depth >= memo_entry.Depth:
            Agent.memo[hash_val] = Agent.MemoEntry(max_val, depth, memo_type, best_move.to_reduced_move_info())

        return max_val

    @staticmethod
    def find_best_move(game: GameState, depth: int, start_time: int, time_limit: int, hash_val: int, alpha = -1_000_000_000, beta = 1_000_000_000) -> Optional[Tuple[MoveInfo, int]]:
        # memo = {} # C# memo = []

        if time.perf_counter() - start_time > time_limit:
            return None
        
        max_val = -1_000_000_000 #-sys.maxsize

        # Agent.killer_moves = [[None, None] for _ in range(Agent.MAX_SEARCH_DEPTH)]
        # Agent.history_table = [[[[0 for _ in range(5)] for _ in range(5)] for _ in range(5)] for _ in range(5)]

        moves = MoveGenerator.generate_moves(game, Agent.MemoEntry.Default, 0)
        best_move = None
        
        for (from_pos, to_pos), is_checking in moves:
            info = game._move(from_pos, to_pos)
            if not info.IsLegal:
                game.undo_move(info)
                continue

            new_hash = GameState.Zobrist.update_hash(hash_val, info)
            DrawDetector.do(new_hash)
            
            value = Agent._negamax(game, -beta, -alpha, depth - 1, 1, new_hash, start_time, time_limit, is_checking)
            value = Agent._negate(value)
            
            DrawDetector.undo(new_hash)
            game.undo_move(info)

            if value is None: # !! Timeout !!
                return None

            if value > max_val:
                best_move = info
                max_val = value

            alpha = max(alpha, value)

            if alpha >= beta:
                break

        return best_move, max_val


### == Here marks the end of the translated C# agent == ###
### == Celebrate for the beffudlement has come to an end == ###
### == Below is conversion from chessmaker types to our agent types == ###


state: GameState = GameState()  # Global game state for the agent


def piece_to_symbol(piece: CM_Piece | None) -> str:
    if piece is None:
        return '.'

    name: str = piece.name
    player: str = piece.player.name

    if name == 'Knight':
        symbol = 'N'
    elif name == 'Pawn' and piece._moved_turns_ago == -1:
        symbol = 'T'
    else:
        symbol = name[0]

    return symbol if player == "white" else symbol.lower()


def find_en_passant_target(board: CM_Board, piece: CM_Piece) -> CM_Position | None:
    if piece is None or piece.name != 'Pawn' or piece.player == board.current_player:
        return None
    
    pawn = piece # pawn: Pawn = piece
    two_squares_behind = pawn.position.offset(0, -2 * pawn._direction.value)
    one_square_behind = pawn.position.offset(0, -1 * pawn._direction.value)

    if (pawn._last_position == two_squares_behind and 0 <= pawn._moved_turns_ago <= 1):
        return one_square_behind


def equal_position(cm_pos: CM_Position, cs_pos: Position) -> bool:
    return cs_pos == to_cs_position(cm_pos)


def to_cs_position(cm_pos: CM_Position) -> Position:
    return Position(cm_pos.x, 4 - cm_pos.y)


def find_move_on_cm_board(board: CM_Board, move: MoveInfo) -> CM_Move:
    piece: CM_Piece | None = None
    for p in board.get_player_pieces(board.current_player):
        if equal_position(p.position, move.From):
            piece = p
            break

    move_opt: CM_MoveOption | None = None
    for m in piece.get_move_options():
        to: CM_Position = m.position
        if equal_position(to, move.To):
            move_opt = m
            break

    assert piece is not None, "Piece not found on CM board"
    assert move_opt is not None, "Move option not found on CM board"

    return piece, move_opt

def capture_state(state: GameState) -> str:
    board_str = str(state)
    # also need to capture: repetition history
    return board_str + '\n' + str(DrawDetector.positions)


def agent(board: CM_Board, player: CM_Player, var: list[int]) -> CM_Move:
    """
    This is an example of your designed Agent

    Parameters
    ----------
    board: the current chess board
    player: your assigned player role (white or black)
    var:  [ply, THINKING_TIME_BUDGET] a list cotaining the ply ID and the thinking_time_budget (secs)

    Returns
    -------
    piece: your selected chess piece
    move_opt: your selected move of your selected chess piece
    
    Hints:
    -----
    - List of players on the current board game: list(board.players) - default list: [Player (white), Player (black)]
    - board.players[0].name = "white" and board.players[1].name = "black"
    - Name of the player assigned to the Agent (either "white" or "black"): player.name
    - list of pieces of the current player: list(board.get_player_pieces(player))
    - List of pieces and corresponding moves for each pieces of the player: piece, move_opt = list_legal_moves_for(board, player)
    - From var: ply ID = var[0], timeout = var[1]
    - Use the timeout variable together with time.perf_counter()
    to ensure the agent returns its best move before the time limit expires.
    """
    start_time = time.perf_counter()

    global state
    cm_board: CM_Board = board
    cm_player: CM_Player = player
    ply_id: int = var[0]
    timeout: float = var[1] - 0.1
    
    take_notes(f"=== Ply {ply_id} ({player}) ===")

    # CRITICAL: maybe the process is persistent, so we musnt allow the state to accumulate
    if ply_id <= 1:
        DrawDetector.positions.clear()
        Agent.memo.clear()
        Agent.killer_moves = [[None, None] for _ in range(Agent.MAX_SEARCH_DEPTH)]
        Agent.history_table = [[[[0 for _ in range(5)] for _ in range(5)] for _ in range(5)] for _ in range(5)]

    # Rip out the state from private attributes and methods from chessmaker
    # into our GameState
    epTarget: CM_Position | None = None
    for row in cm_board._squares:
        for square in row:
            piece: CM_Piece | None = square.piece
            position: CM_Position = square.position
            symbol = piece_to_symbol(piece)
            pos = to_cs_position(position)
            state.board[pos] = symbol

            if epTarget is None:
                epTarget = find_en_passant_target(cm_board, piece)

            if symbol == 'K':
                state.whiteKing = pos
            elif symbol == 'k':
                state.blackKing = pos


    state.enPassantTarget = Position(epTarget.x, epTarget.y) if epTarget is not None else Position.Null
    state.whiteToMove = (cm_player.name == "white")

    # == Iterative deepening loop ==

    best_move_so_far = None
    best_value = -1_000_000_000
    is_mating: bool
    depth = 0

    hash_val = GameState.Zobrist.compute_hash(state)
    DrawDetector.do(hash_val)  # do opponents move

    while True:
        depth += 1
            
        take_notes(f"Searching depth {depth}...")

        # --- Aspiration Window Logic ---
        # we will try 25 centipawn windows around the last best value
        alpha = best_value - 25 
        beta = best_value + 25

        res = Agent.find_best_move(state, depth, start_time, timeout, hash_val, alpha, beta)
        if res is None:
            take_notes(f"Timeout imminent. Returning best move from depth {depth - 1}")
            break

        move, value = res

        # 3. Check if the search "failed"
        if value <= alpha or value >= beta:
            take_notes(f"  Aspiration failed (a={alpha}, b={beta}, v={value}). Re-searching with full window...")
            # 4. Re-search with a full window
            alpha = -1_000_000_000
            beta =  1_000_000_000
            res = Agent.find_best_move(state, depth, start_time, timeout, hash_val, alpha, beta)
            if res is None:
                take_notes(f"Timeout imminent. Returning best move from depth {depth - 1}")
                break
            move, value = res
        # --- End of Aspiration Logic ---

        best_move_so_far = move
        best_value = value

        # Check for forced mate
        if value >= 10_000: # if the algorithm is optimal <=> is_mating = value == (10_000 + depth - 1), but LMR, futility and null move pruning all make it non-optimal
            take_notes(f"Found mate at depth {depth}!")
            break # No need to search deeper

    # --- END OF LOOP ---
    
    move = best_move_so_far
    value = best_value

    DrawDetector.do(GameState.Zobrist.update_hash(hash_val, move))  # do our move


    # DELETE AFTER DEBUG: VERY MUCH A WASTE OF TIME
    is_checking = MoveGenerator._move_causes_check(state, PositionPair(move.From, move.To))
    is_mating = value == 10_001

    move_suffix = ""
    if is_checking and is_mating:
        move_suffix = "#"
    elif is_mating:
        move_suffix = "§"
    elif is_checking:
        move_suffix = "+"
        
    take_notes(f"{player} moved from {move.From} ({move.FromPiece}) to {move.To} ({move.ToPiece}){move_suffix} with eval {value}")

    return find_move_on_cm_board(cm_board, move)