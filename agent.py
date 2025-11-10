import time
from extension.board_utils import list_legal_moves_for, copy_piece_move, take_notes
from extension.board_rules import only_2kings, cannot_move
from chessmaker.chess.base import Board as CM_Board, Player as CM_Player, Piece as CM_Piece, MoveOption as CM_MoveOption, Position as CM_Position, Square as CM_Square
from chessmaker.chess.pieces import King as CM_King
from typing import Iterable

type CM_Move = tuple[CM_Piece, CM_MoveOption]


### == Below be the C# agent translated into Python == ###
### == Beware of befuddling code == ###
### == Agent function at bottom of file == ###

import sys
import enum
import random
import time
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, Iterable, NamedTuple, Set
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
    EP: Position  # The piece position captured by en passant
    EPPiece: str  # The piece captured by en passant
    IsChecking: bool
    IsMating: bool
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
    IsChecking=False,
    IsMating=False,
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
        print(str(self))


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
            GameState.Zobrist.zobrist_table = [[[GameState.Zobrist._random_ulong() for _ in range(13)] for _ in range(5)] for _ in range(5)]
        
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

            # XOR out the piece from its old square
            current ^= GameState.Zobrist.zobrist_table[move.From.x][move.From.y][from_index]

            # XOR out the captured piece (if any)
            if to_index != -1:
                current ^= GameState.Zobrist.zobrist_table[move.To.x][move.To.y][to_index]

            # XOR out the en passant captured pawn (if any)
            if move.EPPiece != '.':
                current ^= GameState.Zobrist.zobrist_table[move.EP.x][move.EP.y][ep_index]

            # XOR in the piece at its new square
            # Handle promotion
            if move.IsPromotion:
                promoted_piece_index = GameState.Zobrist.index_of('Q' if move.FromPiece.isupper() else 'q')
                current ^= GameState.Zobrist.zobrist_table[move.To.x][move.To.y][promoted_piece_index]
            else:
                current ^= GameState.Zobrist.zobrist_table[move.To.x][move.To.y][from_index]


            # STATE CHANGES

            # XOR the side to move
            current ^= GameState.Zobrist.black_to_move

            # XOR out the old en passant square (if any)
            if move.PreviousEnPassantTarget.is_valid():
                current ^= GameState.Zobrist.zobrist_table[move.PreviousEnPassantTarget.x][move.PreviousEnPassantTarget.y][12]

            # XOR in the new en passant square (if any)
            if move.NewEnPassantTarget.is_valid():
                current ^= GameState.Zobrist.zobrist_table[move.NewEnPassantTarget.x][move.NewEnPassantTarget.y][12]

            return current

        @staticmethod
        def index_of(piece: str) -> int:
            return {
                'P': 0, 'N': 1, 'B': 2, 'R': 3, 'Q': 4, 'K': 5,
                'p': 6, 'n': 7, 'b': 8, 'r': 9, 'q': 10, 'k': 11,
                '*': 12, # en passant marker
            }.get(piece, -1)

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
    
    def current_player_is_in_check(self) -> bool:
        current_king = self.whiteKing if self.whiteToMove else self.blackKing
        return self._square_is_attacked(current_king, not self.whiteToMove)
    
    def current_player_is_mated(self) -> bool:
        return not any(self.get_legal_moves(limit_depth=True))

    def is_drawn_by_only_kings(self) -> bool:
        return all(p == '.' or p == 'K' or p == 'k' for p, pos in self.get_positions())

    def _move(self, move_from: Position, move_to: Position, limit_depth: bool = False) -> MoveInfo:
        from_piece = self.board[move_from]
        to_piece = self.board[move_to]
        ep_piece = '.'
        en_passant_taken = Position.Null
        previous_en_passant_target = self.enPassantTarget
        self.enPassantTarget = Position.Null

        is_promotion = False
        if from_piece == 'P' or from_piece == 'p':
            if move_to.y == 0 or move_to.y == 4:
                is_promotion = True
            elif (move_from.y == 1 and move_to.y == 3) or (move_from.y == 3 and move_to.y == 1):
                self.enPassantTarget = Position(move_from.x, (move_from.y + move_to.y) // 2)
            elif move_to == previous_en_passant_target:
                en_passant_taken = Position(previous_en_passant_target.x, previous_en_passant_target.y + (-1 if self.whiteToMove else 1))
                ep_piece = self.board[en_passant_taken]
                self.board[en_passant_taken] = '.'

        self.board[move_to] = 'Q' if is_promotion and self.whiteToMove else 'q' if is_promotion else from_piece
        self.board[move_from] = '.'

        if from_piece == 'K':
            self.whiteKing = move_to
        elif from_piece == 'k':
            self.blackKing = move_to

        # check legality first
        is_legal = not self.current_player_is_in_check()
        is_check = False
        is_mate = False

        if is_legal:
            is_check = self._opponent_is_in_check()

        # finally switch sides for next move
        self.whiteToMove = not self.whiteToMove

        return MoveInfo(
            From=move_from,
            FromPiece=from_piece,
            To=move_to,
            ToPiece=to_piece,
            EP=en_passant_taken,
            EPPiece=ep_piece,
            IsChecking=is_check,
            IsMating=is_mate,
            IsPromotion=is_promotion,
            IsLegal=is_legal,
            PreviousEnPassantTarget=previous_en_passant_target,
            NewEnPassantTarget=self.enPassantTarget
        )

    def apply_move(self, info: MoveInfo):
        self.board[info.To] = ('Q' if self.whiteToMove else 'q') if info.IsPromotion else info.FromPiece
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
        for move in self.get_moves():
            move_info = self._move(move.From, move.To, limit_depth)
            self.undo_move(move_info)  # _move modifies state, so we undo
            if move_info.IsLegal:
                yield move_info

    def get_moves(self) -> Iterable[PositionPair]:
        pieces = self._get_pieces_for_current_player()
        for piece, pos in pieces:
            if piece == 'P' or piece == 'p':
                yield from self._get_pawn_moves(pos)
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
            if attacker_pos.is_valid() and self.board[attacker_pos] == pawn_piece:
                return True

        # Check king attacks
        for delta in GameState.queenDirections:
            attacker_pos = pos + delta
            if attacker_pos.is_valid() and self.board[attacker_pos] == king_piece:
                return True

        return False

    def _get_pawn_moves(self, pos: Position) -> Iterable[PositionPair]:
        direction = 1 if self.whiteToMove else -1
        start_rank = 0 + direction if self.whiteToMove else 4 + direction
        
        forward_one = Position(pos.x, pos.y + direction)
        if forward_one.is_valid() and self.board[forward_one] == '.':
            yield PositionPair(pos, forward_one)
            forward_two = Position(pos.x, pos.y + 2 * direction)
            if pos.y == start_rank and self.board[forward_two] == '.':
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


# =============================================================================
# Agent.cs
# =============================================================================
class Agent:
    
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

    memo: Dict[int, MemoEntry] = {}

    @staticmethod
    def _piece_to_points(piece: str) -> int:
        return {
            'P': 1, 'p': 1,
            'N': 3, 'n': 3,
            'B': 3, 'b': 3,
            'R': 5, 'r': 5,
            'Q': 9, 'q': 9,
            'K': 0, 'k': 0,
        }.get(piece, 0)

    @staticmethod
    def _heuristic(game: GameState) -> int:
        heuristic = 0
        for piece, pos in game.get_positions():
            is_for = game.piece_is_movers(piece)
            value = Agent._piece_to_points(piece)
            heuristic += value if is_for else -value
        return heuristic

    @staticmethod
    def _negamax(game: GameState, alpha: int, beta: int, depth: int, move_made: MoveInfo, hash_val: int) -> int:
        if DrawDetector.is_drawn(hash_val):
            return 0

        # if move_made.IsMating:  # YOU have been mated, negative score, VERY BAD!!!!
        #     return -(1000 + depth)  # prefer faster mates

        if depth == 0:
            return Agent._heuristic(game)
        
        memo_entry = Agent.memo.get(hash_val)
        if memo_entry and memo_entry.Depth >= depth:
            if memo_entry.Type == Agent.MemoEntryType.Exact:
                return memo_entry.Value
            elif memo_entry.Type == Agent.MemoEntryType.LowerBound and memo_entry.Value >= beta:
                return memo_entry.Value
            elif memo_entry.Type == Agent.MemoEntryType.UpperBound and memo_entry.Value <= alpha:
                return memo_entry.Value
        
        # Use default if no entry
        memo_entry = memo_entry or Agent.MemoEntry.Default


        if game.is_drawn_by_only_kings():
            return 0

        max_val = -sys.maxsize
        best_move = MoveInfo.Default
        initial_alpha = alpha
        is_first_move = True

        moves = game.get_legal_moves()
        sorted_moves = sorted(moves, key=lambda m: Agent._key_selector(m, memo_entry), reverse=True)

        for info in sorted_moves:
            # LMR
            new_depth = depth - 1
            if DrawDetector.moves_made() > 8 and not is_first_move and depth >= 3 and info.ToPiece == '.' and not info.IsChecking and not info.IsMating and not info.IsPromotion:
                new_depth -= 1

            new_hash = GameState.Zobrist.update_hash(hash_val, info)

            game.apply_move(info)
            DrawDetector.do(new_hash)

            value = 0
            if is_first_move:  # PVS (Principal Variation Search)
                value = -Agent._negamax(game, -beta, -alpha, new_depth, info, new_hash)
                is_first_move = False
            else:
                value = -Agent._negamax(game, -(alpha + 1), -alpha, new_depth, info, new_hash)
                if value > alpha:
                    # promote to PV
                    new_depth = depth - 1
                    value = -Agent._negamax(game, -beta, -alpha, new_depth, info, new_hash)

            DrawDetector.undo(new_hash)
            game.undo_move(info)

            if value > max_val:
                max_val = value
                best_move = info
            
            alpha = max(alpha, value)
            if alpha >= beta or info.IsMating:
                break
        
        if best_move == MoveInfo.Default:
            return -(1000 + depth) # no legal moves, you have been mated

        memo_type = Agent.MemoEntryType.Exact
        if max_val <= initial_alpha:
            memo_type = Agent.MemoEntryType.UpperBound
        elif max_val >= beta:
            memo_type = Agent.MemoEntryType.LowerBound
        
        Agent.memo[hash_val] = Agent.MemoEntry(max_val, depth, memo_type, best_move.to_reduced_move_info())

        return max_val

    @staticmethod
    def _key_selector(move_info: MoveInfo, memo_entry: 'Agent.MemoEntry') -> int:
        # Checkmate > Hash Move > Check > Good Capture > Special Move > Bad Capture > Quiet Move
        score = 0

        if move_info.IsMating:
            score += 1_000_000

        if memo_entry.Valid and (move_info.From, move_info.To) == (memo_entry.Move.From, memo_entry.Move.To):
            score += 500_000
        elif move_info.IsChecking:
            score += 100_000

        victim_piece = move_info.ToPiece if move_info.ToPiece != '.' else move_info.EPPiece
        if victim_piece != '.':
            victim = Agent._piece_to_points(victim_piece)
            aggressor = Agent._piece_to_points(move_info.FromPiece)
            score += 10 * victim - aggressor
            
            if victim > aggressor:  # Good capture
                score += 10_000
            else:                   # Bad capture
                score += 100

        if move_info.IsPromotion:
            score += 5000

        return score

    @staticmethod
    def find_best_move(game: GameState) -> Tuple[MoveInfo, int]:
        depth = 5  # C# const int depth = 11

        # memo = {} # C# memo = []

        moves = sorted(game.get_legal_moves(), key=lambda m: Agent._key_selector(m, Agent.MemoEntry.Default), reverse=True)

        best_move = moves[0]
        max_val = -1_000_000_000 #-sys.maxsize
        alpha = -1_000_000_000 #-sys.maxsize
        beta = 1_000_000_000 #sys.maxsize
        hash_val = GameState.Zobrist.compute_hash(game)

        DrawDetector.do(hash_val)  # do opponents move

        for info in moves:
            new_hash = GameState.Zobrist.update_hash(hash_val, info)
            game.apply_move(info)
            DrawDetector.do(new_hash)
            
            value = -Agent._negamax(game, -beta, -alpha, depth - 1, info, new_hash)
            
            DrawDetector.undo(new_hash)
            game.undo_move(info)

            if value > max_val:
                best_move = info
                max_val = value

            alpha = max(alpha, value)

            if alpha >= beta or info.IsMating:
                break
        
        DrawDetector.do(GameState.Zobrist.update_hash(hash_val, best_move))  # do best move

        return best_move, max_val


# =============================================================================
# Program.cs
# =============================================================================
def test_agent_game(game: GameState):
    game.print_board()
    print("======")

    while True:
        player = "White" if game.piece_is_movers('K') else "Black"
        if game.is_drawn_by_only_kings():
            print("Draw by 2 kings remaining")
            break
        if DrawDetector.check_for_draw():
            print("Draw by repetition")
            break
        if game.current_player_is_mated():
            print(f"{player} is mated")
            break

        move, value = Agent.find_best_move(game)

        game.apply_move(move)
        
        check_str = ""
        if move.IsChecking:
            check_str = "#" if move.IsMating else "+"
        elif move.IsMating:
            check_str = "§" # C# code had this, preserving
            
        print(f"{player} moved from {move.From} ({move.FromPiece}) to {move.To} ({move.ToPiece}){check_str} with eval {value}")
        game.print_board()
        print("======")

if __name__ == "__main__":
    g2 = GameState(
        """
. Q . . .
. . . . k
. . R . .
. P . . .
. . . K N
""", 
        whiteToMove=False
    )  # mate in 2

    g3 = GameState(
        """
. . . . k
. Q . . .
. . R . .
. P . . .
. . . K N
"""
    )  # mate in 1

    # test_agent_game(g2)

    start_time = time.perf_counter()
    test_agent_game(GameState())
    end_time = time.perf_counter()
    
    ts = end_time - start_time
    minutes = int(ts // 60)
    seconds = ts % 60
    
    print(f"Time taken: {minutes:02}:{seconds:05.2f}")


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
    global state
    cm_board: CM_Board = board
    cm_player: CM_Player = player
    ply_id: int = var[0]
    timeout: float = var[1]

    # Rip out the state from private attributes and methods from chessmaker
    # into our GameState
    epTarget: CM_Position | None = None
    for row in cm_board._squares:
        for square in row:
            if square is None:
                raise ValueError("Square is None")
            piece: CM_Piece | None = square.piece
            position: CM_Position = square.position
            symbol = piece_to_symbol(piece)
            state.board[to_cs_position(position)] = symbol

            if epTarget is None:
                epTarget = find_en_passant_target(cm_board, piece)

    state.enPassantTarget = Position(epTarget.x, epTarget.y) if epTarget is not None else Position.Null
    state.whiteToMove = (cm_player.name == "white")

    move, value = Agent.find_best_move(state)

    check_str = ""
    if move.IsChecking:
        check_str = "#" if move.IsMating else "+"
    elif move.IsMating:
        check_str = "§"
        
    print(f"{player} moved from {move.From} ({move.FromPiece}) to {move.To} ({move.ToPiece}){check_str} with eval {value}")

    return find_move_on_cm_board(cm_board, move)