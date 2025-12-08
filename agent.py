from extension.board_utils import take_notes
from chessmaker.chess.base import Board as CM_Board, Player as CM_Player, Piece as CM_Piece, MoveOption as CM_MoveOption, Position as CM_Position, Square as CM_Square
from typing import Iterable

type CM_Move = tuple[CM_Piece, CM_MoveOption]

### == Below be the C# agent translated into Python == ###
### == REWRITTEN TO USE BITBOARDS FOR PERFORMANCE == ###
### == Agent function at bottom of file == ###

import math
import enum
import random
import time
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, NamedTuple
from functools import total_ordering

# =============================================================================
# Bitboard Constants & Helpers
# =============================================================================

# Board Mapping:
# 20 21 22 23 24  (Rank 4)
# 15 16 17 18 19  (Rank 3)
# 10 11 12 13 14  (Rank 2)
# 05 06 07 08 09  (Rank 1)
# 00 01 02 03 04  (Rank 0)

MASK_ALL = 0x1FFFFFF  # 25 bits
FILE_A = 0x108421
FILE_B = 0x210842
FILE_C = 0x421084
FILE_D = 0x842108
FILE_E = 0x1084210
RANK_0 = 0x1F
RANK_1 = 0x3E0
RANK_2 = 0x7C00
RANK_3 = 0xF8000
RANK_4 = 0x1F00000

# Precomputed Attacks
KNIGHT_ATTACKS = [0] * 25
KING_ATTACKS = [0] * 25
# [sq][0=N, 1=E, 2=S, 3=W, 4=NE, 5=SE, 6=SW, 7=NW]
RAYS = [[0] * 8 for _ in range(25)]

def _init_tables():
    knight_offsets = [(2, 1), (1, 2), (-1, 2), (-2, 1), (-2, -1), (-1, -2), (1, -2), (2, -1)]
    king_offsets = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
    dirs = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, -1), (-1, 1)] # N, E, S, W, NE, SE, SW, NW

    for sq in range(25):
        x, y = sq % 5, sq // 5
        
        # Knight
        k_mask = 0
        for dx, dy in knight_offsets:
            nx, ny = x + dx, y + dy
            if 0 <= nx < 5 and 0 <= ny < 5:
                k_mask |= (1 << (ny * 5 + nx))
        KNIGHT_ATTACKS[sq] = k_mask

        # King
        k_mask = 0
        for dx, dy in king_offsets:
            nx, ny = x + dx, y + dy
            if 0 <= nx < 5 and 0 <= ny < 5:
                k_mask |= (1 << (ny * 5 + nx))
        KING_ATTACKS[sq] = k_mask

        # Rays
        for i, (dx, dy) in enumerate(dirs):
            r_mask = 0
            cx, cy = x + dx, y + dy
            while 0 <= cx < 5 and 0 <= cy < 5:
                r_mask |= (1 << (cy * 5 + cx))
                cx += dx
                cy += dy
            RAYS[sq][i] = r_mask

_init_tables()

def pop_lsb(mask: int) -> Tuple[int, int]:
    """Returns (bit_index, new_mask)"""
    lsb = mask & -mask
    return lsb.bit_length() - 1, mask ^ lsb

def count_bits(mask: int) -> int:
    return mask.bit_count()


# =============================================================================
# Position.cs (Legacy wrapper for API compatibility)
# =============================================================================
@total_ordering
class Position:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    @staticmethod
    def from_index(idx: int) -> 'Position':
        if idx < 0: return Position.Null
        return Position(idx % 5, idx // 5)

    def to_index(self) -> int:
        if not self.is_valid(): return -1
        return self.y * 5 + self.x

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
    EP=Position.Null, EPPiece='.', PromotionPiece='.',
    IsPromotion=False, IsLegal=False,
    PreviousEnPassantTarget=Position.Null, NewEnPassantTarget=Position.Null
)

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
# GameState.cs (Bitboard Implementation)
# =============================================================================
class GameState:
    
    # --- Zobrist.cs ---
    class Zobrist:
        _random = random.Random(0)
        zobrist_table: List[List[List[int]]] = []
        black_to_move: int = 0
        
        @staticmethod
        def _random_ulong() -> int:
            return GameState.Zobrist._random.getrandbits(64)

        @staticmethod
        def _initialize():
            GameState.Zobrist.black_to_move = GameState.Zobrist._random_ulong()
            # 5x5 board, 15 piece types (including EP marker at index 14)
            GameState.Zobrist.zobrist_table = [[[GameState.Zobrist._random_ulong() for _ in range(15)] for _ in range(5)] for _ in range(5)]
        
        @staticmethod
        def compute_hash(game: 'GameState') -> int:
            h = 0
            # Reconstruct board iteration from bitboards
            for sq in range(25):
                piece = game.get_piece_at_index(sq)
                if piece != '.':
                    pidx = GameState.Zobrist.index_of(piece)
                    x, y = sq % 5, sq // 5
                    h ^= GameState.Zobrist.zobrist_table[x][y][pidx]

            if not game.whiteToMove:
                h ^= GameState.Zobrist.black_to_move
            
            if game.enPassantTarget.is_valid():
                h ^= GameState.Zobrist.zobrist_table[game.enPassantTarget.x][game.enPassantTarget.y][14]
            return h

        @staticmethod
        def update_hash(current: int, move: MoveInfo) -> int:
            # Same logic as before, just Zobrist values
            from_index = GameState.Zobrist.index_of(move.FromPiece)
            to_index = GameState.Zobrist.index_of(move.ToPiece)
            ep_index = GameState.Zobrist.index_of(move.EPPiece)
            promo_index = GameState.Zobrist.index_of(move.PromotionPiece)

            current ^= GameState.Zobrist.zobrist_table[move.From.x][move.From.y][from_index]
            if to_index != -1:
                current ^= GameState.Zobrist.zobrist_table[move.To.x][move.To.y][to_index]
            if move.EPPiece != '.':
                current ^= GameState.Zobrist.zobrist_table[move.EP.x][move.EP.y][ep_index]
            current ^= GameState.Zobrist.zobrist_table[move.To.x][move.To.y][promo_index]

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
            map_ = {'T':0, 'P':1, 'N':2, 'B':3, 'R':4, 'Q':5, 'K':6,
                    't':7, 'p':8, 'n':9, 'b':10, 'r':11, 'q':12, 'k':13, '*':14}
            return map_.get(piece, -1)

    # --- Bitboard State ---
    # White pieces
    bb_W_P: int; bb_W_T: int; bb_W_N: int; bb_W_B: int; bb_W_R: int; bb_W_Q: int; bb_W_K: int
    # Black pieces
    bb_B_p: int; bb_B_t: int; bb_B_n: int; bb_B_b: int; bb_B_r: int; bb_B_q: int; bb_B_k: int
    
    # Aggregates
    bb_White: int; bb_Black: int; bb_All: int

    enPassantTarget: Position
    whiteToMove: bool
    whiteKing: Position
    blackKing: Position

    def __init__(self, setup: Optional[str] = None, whiteToMove: bool = True):
        self.whiteToMove = whiteToMove
        self.enPassantTarget = Position.Null
        self._clear_bitboards()

        if setup is None:
            setup = "n q k b r\np p p p p\n. . . . .\nP P P P P\nR B K Q N"

        self._parse_setup(setup)
        self._update_aggregates()

        if not GameState.Zobrist.zobrist_table:
            GameState.Zobrist._initialize()

    def _clear_bitboards(self):
        self.bb_W_P = self.bb_W_T = self.bb_W_N = self.bb_W_B = self.bb_W_R = self.bb_W_Q = self.bb_W_K = 0
        self.bb_B_p = self.bb_B_t = self.bb_B_n = self.bb_B_b = self.bb_B_r = self.bb_B_q = self.bb_B_k = 0
        self.bb_White = self.bb_Black = self.bb_All = 0

    def _parse_setup(self, string_board: str):
        rows = string_board.strip().split('\n')
        for r in range(5):
            cols = rows[5 - r - 1].strip().split(' ')
            for c in range(5):
                piece = cols[c][0]
                idx = r * 5 + c
                bit = 1 << idx
                if piece == '.': continue
                
                if piece == 'P': self.bb_W_P |= bit
                elif piece == 'T': self.bb_W_T |= bit
                elif piece == 'N': self.bb_W_N |= bit
                elif piece == 'B': self.bb_W_B |= bit
                elif piece == 'R': self.bb_W_R |= bit
                elif piece == 'Q': self.bb_W_Q |= bit
                elif piece == 'K': 
                    self.bb_W_K |= bit
                    self.whiteKing = Position(c, r)
                elif piece == 'p': self.bb_B_p |= bit
                elif piece == 't': self.bb_B_t |= bit
                elif piece == 'n': self.bb_B_n |= bit
                elif piece == 'b': self.bb_B_b |= bit
                elif piece == 'r': self.bb_B_r |= bit
                elif piece == 'q': self.bb_B_q |= bit
                elif piece == 'k': 
                    self.bb_B_k |= bit
                    self.blackKing = Position(c, r)

    def _update_aggregates(self):
        self.bb_White = self.bb_W_P | self.bb_W_T | self.bb_W_N | self.bb_W_B | self.bb_W_R | self.bb_W_Q | self.bb_W_K
        self.bb_Black = self.bb_B_p | self.bb_B_t | self.bb_B_n | self.bb_B_b | self.bb_B_r | self.bb_B_q | self.bb_B_k
        self.bb_All = self.bb_White | self.bb_Black

    def get_piece_at_index(self, idx: int) -> str:
        bit = 1 << idx
        if not (self.bb_All & bit): return '.'
        if self.bb_White & bit:
            if self.bb_W_P & bit: return 'P'
            if self.bb_W_T & bit: return 'T'
            if self.bb_W_N & bit: return 'N'
            if self.bb_W_B & bit: return 'B'
            if self.bb_W_R & bit: return 'R'
            if self.bb_W_Q & bit: return 'Q'
            if self.bb_W_K & bit: return 'K'
        else:
            if self.bb_B_p & bit: return 'p'
            if self.bb_B_t & bit: return 't'
            if self.bb_B_n & bit: return 'n'
            if self.bb_B_b & bit: return 'b'
            if self.bb_B_r & bit: return 'r'
            if self.bb_B_q & bit: return 'q'
            if self.bb_B_k & bit: return 'k'
        return '.'

    # Emulate __getitem__ for compatibility
    def __getitem__(self, key) -> str:
        if isinstance(key, Position):
            return self.get_piece_at_index(key.y * 5 + key.x)
        elif isinstance(key, tuple):
            return self.get_piece_at_index(key[1] * 5 + key[0])
        raise TypeError("Invalid key")

    # Set item for setup/compatibility (though pure bitboard methods prefer apply_move)
    def __setitem__(self, key, value: str):
        pos = key if isinstance(key, Position) else Position(key[0], key[1])
        idx = pos.y * 5 + pos.x
        bit = 1 << idx
        
        # Clear existing
        self.bb_W_P &= ~bit; self.bb_W_T &= ~bit; self.bb_W_N &= ~bit
        self.bb_W_B &= ~bit; self.bb_W_R &= ~bit; self.bb_W_Q &= ~bit; self.bb_W_K &= ~bit
        self.bb_B_p &= ~bit; self.bb_B_t &= ~bit; self.bb_B_n &= ~bit
        self.bb_B_b &= ~bit; self.bb_B_r &= ~bit; self.bb_B_q &= ~bit; self.bb_B_k &= ~bit

        if value != '.':
            if value == 'P': self.bb_W_P |= bit
            elif value == 'T': self.bb_W_T |= bit
            elif value == 'N': self.bb_W_N |= bit
            elif value == 'B': self.bb_W_B |= bit
            elif value == 'R': self.bb_W_R |= bit
            elif value == 'Q': self.bb_W_Q |= bit
            elif value == 'K': self.bb_W_K |= bit
            elif value == 'p': self.bb_B_p |= bit
            elif value == 't': self.bb_B_t |= bit
            elif value == 'n': self.bb_B_n |= bit
            elif value == 'b': self.bb_B_b |= bit
            elif value == 'r': self.bb_B_r |= bit
            elif value == 'q': self.bb_B_q |= bit
            elif value == 'k': self.bb_B_k |= bit
        
        self._update_aggregates()

    def piece_is_movers(self, piece: str) -> bool:
        return piece.isupper() == self.whiteToMove

    def _opponent_is_in_check(self) -> bool:
        king_pos = self.blackKing if self.whiteToMove else self.whiteKing
        if king_pos.is_null(): return False # Should not happen
        return self._square_is_attacked(king_pos.to_index(), self.whiteToMove)
    
    def _current_player_is_in_check(self) -> bool:
        king_pos = self.whiteKing if self.whiteToMove else self.blackKing
        if king_pos.is_null(): return False
        return self._square_is_attacked(king_pos.to_index(), not self.whiteToMove)
    
    def current_player_is_mated(self) -> bool:
        return not any(self.get_legal_moves())

    def is_drawn_by_only_kings(self) -> bool:
        return self.bb_All == (self.bb_W_K | self.bb_B_k)

    def _move(self, move_from: Position, move_to: Position) -> MoveInfo:
        # Replicates logic but uses board state
        from_idx = move_from.to_index()
        to_idx = move_to.to_index()
        from_piece = self.get_piece_at_index(from_idx)
        to_piece = self.get_piece_at_index(to_idx)
        
        ep_piece = '.'
        promotion_piece = from_piece
        en_passant_taken = Position.Null
        previous_en_passant_target = self.enPassantTarget
        self.enPassantTarget = Position.Null

        is_promotion = False
        
        # Logic for P/T/p/t
        if from_piece in ('P', 'p', 'T', 't'):
            if move_to.y == 0 or move_to.y == 4:
                is_promotion = True
                promotion_piece = 'Q' if self.whiteToMove else 'q'
            elif abs(move_to.y - move_from.y) == 2:
                self.enPassantTarget = Position(move_from.x, (move_from.y + move_to.y) // 2)
            elif move_to == previous_en_passant_target:
                # Capture EP
                ep_capture_y = previous_en_passant_target.y + (-1 if self.whiteToMove else 1)
                en_passant_taken = Position(previous_en_passant_target.x, ep_capture_y)
                ep_piece = self[en_passant_taken]
                self[en_passant_taken] = '.'

        # Two-step pawns become normal pawns if they move (and don't promote)
        if (from_piece == 'T' or from_piece == 't') and not is_promotion:
            promotion_piece = 'P' if self.whiteToMove else 'p'

        # Apply Move
        self[move_to] = promotion_piece
        self[move_from] = '.'

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
        self[info.From] = info.FromPiece
        self[info.To] = info.ToPiece
        
        if info.EP.is_valid():
            self[info.EP] = info.EPPiece

        if info.FromPiece == 'K': self.whiteKing = info.From
        elif info.FromPiece == 'k': self.blackKing = info.From

        self.whiteToMove = not self.whiteToMove
        self.enPassantTarget = info.PreviousEnPassantTarget

    def get_legal_moves(self, limit_depth: bool = False) -> Iterable[MoveInfo]:
        # Using the simplified generator logic for compatibility
        for move_pair in self._get_moves_generator():
            move_info = self._move(move_pair.From, move_pair.To)
            self.undo_move(move_info)
            if move_info.IsLegal:
                yield move_info

    def _get_moves_generator(self) -> Iterable[PositionPair]:
        # Uses bitboard move generation logic
        return MoveGenerator.get_pseudo_legal_moves(self)

    def _square_is_attacked(self, sq_idx: int, by_white: bool) -> bool:
        # Determine attackers bitboards
        if by_white:
            pawns = self.bb_W_P | self.bb_W_T
            knights = self.bb_W_N
            bishops = self.bb_W_B
            rights = self.bb_W_R
            queens = self.bb_W_Q
            king = self.bb_W_K
            pawn_attack_mask = ((1 << sq_idx) >> 5) & 0x1FFFFFF # White pawns attack UP (from their perspective), so we look DOWN for attackers
            # Actually, standard logic: Pawns on (idx-5-1) and (idx-5+1) attack idx.
            # White pawn attacks: (bb >> 4 & ~FileA) | (bb >> 6 & ~FileE)
            # Reversing: Is 'sq' attacked by a pawn? 
            # If sq is attacked by white pawn, a white pawn must be at sq-4 or sq-6
            # Careful with file wraps.
            
            # Attacked by White Pawn at sq-6 (needs to be not File E for the pawn) -> Pawn is at SouthWest
            # Attacked by White Pawn at sq-4 (needs to be not File A for the pawn) -> Pawn is at SouthEast
            
            # Simple check:
            # Attackers of sq from White Pawns:
            # Down-Left (sq-6) and Down-Right (sq-4)
            p_attackers = 0
            if sq_idx >= 6 and (sq_idx % 5) != 0: p_attackers |= (1 << (sq_idx - 6))
            if sq_idx >= 4 and (sq_idx % 5) != 4: p_attackers |= (1 << (sq_idx - 4))
            if p_attackers & pawns: return True

        else:
            pawns = self.bb_B_p | self.bb_B_t
            knights = self.bb_B_n
            bishops = self.bb_B_b
            rights = self.bb_B_r
            queens = self.bb_B_q
            king = self.bb_B_k
            
            # Black pawns attack DOWN. So we look UP for attackers.
            # Up-Left (sq+4) and Up-Right (sq+6)
            p_attackers = 0
            if sq_idx <= 20 and (sq_idx % 5) != 0: p_attackers |= (1 << (sq_idx + 4))
            if sq_idx <= 18 and (sq_idx % 5) != 4: p_attackers |= (1 << (sq_idx + 6))
            if p_attackers & pawns: return True

        # Knight / Right (Knight moves)
        if KNIGHT_ATTACKS[sq_idx] & (knights | rights): return True
        
        # King
        if KING_ATTACKS[sq_idx] & king: return True

        # Sliders
        occ = self.bb_All
        
        # Rooks / Rights / Queens
        orth_attackers = rights | queens
        if by_white: orth_attackers |= self.bb_W_R # Explicitly add pure rook if it existed (though logic implies R=Right)
        
        if orth_attackers:
            # Raytrace North/South/East/West
            for d in [0, 1, 2, 3]:
                ray = RAYS[sq_idx][d]
                if ray & orth_attackers:
                    # Find first blocker
                    blocker = ray & occ
                    if blocker:
                        # Which bit is the blocker?
                        # N(0), E(1): increasing indices. First blocker is LSB.
                        # S(2), W(3): decreasing indices. First blocker is MSB.
                        b_idx = -1
                        if d < 2: b_idx = (blocker & -blocker).bit_length() - 1
                        else: b_idx = blocker.bit_length() - 1
                        
                        if (1 << b_idx) & orth_attackers: return True

        # Bishops / Queens
        diag_attackers = bishops | queens
        if diag_attackers:
            for d in [4, 5, 6, 7]:
                ray = RAYS[sq_idx][d]
                if ray & diag_attackers:
                    blocker = ray & occ
                    if blocker:
                        b_idx = -1
                        if d == 4 or d == 7: # NE, NW: generally increasing y, check indices
                             # NE (+6), NW (+4). Increasing. LSB.
                             b_idx = (blocker & -blocker).bit_length() - 1
                        else: # SE, SW: Decreasing. MSB.
                             b_idx = blocker.bit_length() - 1
                        
                        if (1 << b_idx) & diag_attackers: return True
        return False

    def get_positions(self) -> Iterable[Tuple[str, Position]]:
        for i in range(25):
            p = self.get_piece_at_index(i)
            yield (p, Position.from_index(i))

    def __str__(self) -> str:
        sb = []
        for r in range(4, -1, -1):
            for c in range(5):
                sb.append(self.get_piece_at_index(r*5 + c))
                sb.append(' ')
            sb.append('\n')
        return "".join(sb) + f"White to move: {self.whiteToMove}\nEn Passant Target: {str(self.enPassantTarget)}\n"


# =============================================================================
# MoveGenerator.cs (Bitboard Edition)
# =============================================================================

class MoveGenerator:
    
    @staticmethod
    def get_pseudo_legal_moves(game: GameState) -> Iterable[PositionPair]:
        """Generator that yields PositionPair for all pseudo-legal moves."""
        
        us_occ = game.bb_White if game.whiteToMove else game.bb_Black
        them_occ = game.bb_Black if game.whiteToMove else game.bb_White
        all_occ = game.bb_All
        
        # --- PAWNS ---
        # Single Pushes, Double Pushes, Captures
        
        pawns_1 = game.bb_W_P if game.whiteToMove else game.bb_B_p
        pawns_2 = game.bb_W_T if game.whiteToMove else game.bb_B_t
        all_pawns = pawns_1 | pawns_2
        
        direction = 5 if game.whiteToMove else -5
        
        # 1. Single Push
        # Shift pawns by direction, mask with ~all_occ
        if game.whiteToMove:
            single_pushes = (all_pawns << 5) & ~all_occ & MASK_ALL
        else:
            single_pushes = (all_pawns >> 5) & ~all_occ & MASK_ALL
            
        temp = single_pushes
        while temp:
            to_idx, temp = pop_lsb(temp)
            from_idx = to_idx - direction
            yield PositionPair(Position.from_index(from_idx), Position.from_index(to_idx))
            
        # 2. Double Push (Only for pawns_2 / 'T'/'t')
        # Condition: Path clear.
        if game.whiteToMove:
            # Shift T by 5, ensure empty, shift by 5 again, ensure empty
            s1 = (pawns_2 << 5) & ~all_occ & MASK_ALL
            s2 = (s1 << 5) & ~all_occ & MASK_ALL
            temp = s2
            while temp:
                to_idx, temp = pop_lsb(temp)
                yield PositionPair(Position.from_index(to_idx - 10), Position.from_index(to_idx))
        else:
            s1 = (pawns_2 >> 5) & ~all_occ & MASK_ALL
            s2 = (s1 >> 5) & ~all_occ & MASK_ALL
            temp = s2
            while temp:
                to_idx, temp = pop_lsb(temp)
                yield PositionPair(Position.from_index(to_idx + 10), Position.from_index(to_idx))

        # 3. Captures
        # White: +6 (NE), +4 (NW). Black: -6 (SW), -4 (SE).
        # Check against them_occ OR EnPassantTarget
        ep_mask = 0
        if game.enPassantTarget.is_valid():
            ep_mask = (1 << game.enPassantTarget.to_index())
        
        targets = them_occ | ep_mask
        
        if game.whiteToMove:
            # Capture NE (+6), avoid File A overlap (source can't be H, here Source can't be E)
            caps = ((all_pawns & ~FILE_E) << 6) & targets & MASK_ALL
            temp = caps
            while temp:
                to_idx, temp = pop_lsb(temp)
                yield PositionPair(Position.from_index(to_idx - 6), Position.from_index(to_idx))
            
            # Capture NW (+4), avoid File A
            caps = ((all_pawns & ~FILE_A) << 4) & targets & MASK_ALL
            temp = caps
            while temp:
                to_idx, temp = pop_lsb(temp)
                yield PositionPair(Position.from_index(to_idx - 4), Position.from_index(to_idx))
        else:
             # Capture SW (-6), avoid File A (source can't be E? No, source can't be A)
             # Source at E (4) -> -6 = -2 invalid. Source at B (1) -> -6 = -5 invalid.
             # Shift right 6: Source must not be File A? No.
             # From B2 (6) -> Right 6 -> 0 (A1). Valid.
             # From A2 (5) -> Right 6 -> -1. Valid.
             # Wait, (Mask & ~FileA) >> 6 means source not on A? 
             # If piece is on A2(5), capture right is -4 to B1(1). Capture left is -6 (invalid).
             # So: Right Capture (-4) requires Source != E. Left Capture (-6) requires Source != A.
             
             # Capture Right-Down (-4): Source != FileE
             caps = ((all_pawns & ~FILE_E) >> 4) & targets & MASK_ALL
             temp = caps
             while temp:
                 to_idx, temp = pop_lsb(temp)
                 yield PositionPair(Position.from_index(to_idx + 4), Position.from_index(to_idx))

             # Capture Left-Down (-6): Source != FileA
             caps = ((all_pawns & ~FILE_A) >> 6) & targets & MASK_ALL
             temp = caps
             while temp:
                 to_idx, temp = pop_lsb(temp)
                 yield PositionPair(Position.from_index(to_idx + 6), Position.from_index(to_idx))

        # --- OTHER PIECES ---
        
        # Knights
        knights = game.bb_W_N if game.whiteToMove else game.bb_B_n
        rights = game.bb_W_R if game.whiteToMove else game.bb_B_r
        knight_movers = knights | rights
        
        temp = knight_movers
        while temp:
            from_idx, temp = pop_lsb(temp)
            moves = KNIGHT_ATTACKS[from_idx] & ~us_occ
            while moves:
                to_idx, moves = pop_lsb(moves)
                yield PositionPair(Position.from_index(from_idx), Position.from_index(to_idx))

        # Bishops / Queens
        bishops = game.bb_W_B if game.whiteToMove else game.bb_B_b
        queens = game.bb_W_Q if game.whiteToMove else game.bb_B_q
        diag_movers = bishops | queens
        
        temp = diag_movers
        while temp:
            from_idx, temp = pop_lsb(temp)
            # Rays: 4,5,6,7
            for d in [4, 5, 6, 7]:
                ray = RAYS[from_idx][d]
                blockers = ray & all_occ
                # Mask out ray after blocker
                valid_ray = ray
                if blockers:
                    if d in [4, 7]: # Increasing
                        first_block = (blockers & -blockers).bit_length() - 1
                        # Mask everything above first_block
                        # Actually simpler: if we hit a blocker, we can include it if it's enemy, but stop after
                        # We need to zero out bits > first_block
                        # Generate mask of bits <= first_block
                        mask_lower = (1 << (first_block + 1)) - 1
                        valid_ray &= mask_lower
                    else: # Decreasing
                        first_block = blockers.bit_length() - 1 # MSB
                        # Mask everything below first_block
                        mask_upper = ~((1 << first_block) - 1)
                        valid_ray &= mask_upper
                
                moves = valid_ray & ~us_occ
                while moves:
                    to_idx, moves = pop_lsb(moves)
                    yield PositionPair(Position.from_index(from_idx), Position.from_index(to_idx))

        # Rooks / Rights / Queens
        orth_movers = rights | queens
        if game.whiteToMove: orth_movers |= game.bb_W_R # should overlap with rights but just in case
        else: orth_movers |= game.bb_B_r

        temp = orth_movers
        while temp:
            from_idx, temp = pop_lsb(temp)
            for d in [0, 1, 2, 3]:
                ray = RAYS[from_idx][d]
                blockers = ray & all_occ
                valid_ray = ray
                if blockers:
                    if d < 2: # Increasing
                        first_block = (blockers & -blockers).bit_length() - 1
                        mask_lower = (1 << (first_block + 1)) - 1
                        valid_ray &= mask_lower
                    else: # Decreasing
                        first_block = blockers.bit_length() - 1
                        mask_upper = ~((1 << first_block) - 1)
                        valid_ray &= mask_upper
                
                moves = valid_ray & ~us_occ
                while moves:
                    to_idx, moves = pop_lsb(moves)
                    yield PositionPair(Position.from_index(from_idx), Position.from_index(to_idx))

        # King
        king = game.bb_W_K if game.whiteToMove else game.bb_B_k
        if king:
            from_idx = (king & -king).bit_length() - 1
            moves = KING_ATTACKS[from_idx] & ~us_occ
            while moves:
                to_idx, moves = pop_lsb(moves)
                yield PositionPair(Position.from_index(from_idx), Position.from_index(to_idx))


    @staticmethod
    def _is_forcing(game: GameState, move: PositionPair) -> bool:
        from_piece = game[move.From]
        to_piece = game[move.To]
        
        is_pawn = from_piece in ('P', 'p', 'T', 't')
        is_promo = is_pawn and (move.To.y == 0 or move.To.y == 4)
        is_ep = is_pawn and move.To == game.enPassantTarget
        is_capture = to_piece != '.' or is_ep

        return is_promo or is_capture

    @staticmethod
    def generate_q_moves(game: GameState, memo_entry: 'Agent.MemoEntry') -> Iterable[PositionPair]:
        hash_move: Optional[ReducedMoveInfo] = None
        
        # FIX: Check if the move positions are valid before processing
        if memo_entry.Valid and memo_entry.Move.From.is_valid():
            hash_move_pair = PositionPair(memo_entry.Move.From, memo_entry.Move.To)
            # Now safe to check _is_forcing because coordinates are valid
            if MoveGenerator._is_forcing(game, hash_move_pair):
                hash_move = memo_entry.Move
                yield hash_move_pair

        PROMO_SCORE = 8_000_000
        CAPTURE_BASE = 7_000_000
        
        q_moves: List[Tuple[int, PositionPair]] = []

        for move in game._get_moves_generator():
            if hash_move and move.From == hash_move.From and move.To == hash_move.To:
                continue
            
            from_piece = game[move.From]
            to_piece = game[move.To]
            
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
        
        q_moves.sort(reverse=True)
        for score, move in q_moves:
            yield move

    @staticmethod
    def generate_moves(game: GameState, memo_entry: 'Agent.MemoEntry', ply: int) -> Iterable[tuple[PositionPair, bool]]:
        # FIX: Check if the move positions are valid
        if memo_entry.Valid and memo_entry.Move.From.is_valid():
            pair = PositionPair(memo_entry.Move.From, memo_entry.Move.To)
            yield pair, MoveGenerator._move_causes_check(game, pair)

        promotions = []
        good_captures = []
        killers = []
        quiet_checks = []
        history_moves = []
        bad_captures = []
        
        k1, k2 = None, None
        if ply < Agent.MAX_SEARCH_DEPTH:
            k1 = Agent.killer_moves[ply][0]
            k2 = Agent.killer_moves[ply][1]

        PROMO_CHECK_SCORE = 9_000_000
        PROMO_SCORE = 8_000_000
        GOOD_CAPTURE_BASE = 7_000_000
        BAD_CAPTURE_BASE = 1_000_000
        CHECK_BONUS = 10_000

        for move in game._get_moves_generator():
            reduced_move = ReducedMoveInfo(move.From, move.To)
            # Check Valid AND is_valid() here too just to be safe, though strict equality with valid moves usually handles it
            if memo_entry.Valid and memo_entry.Move.From.is_valid() and reduced_move == memo_entry.Move:
                continue

            from_piece = game[move.From]
            to_piece = game[move.To]
            is_promo = (from_piece in ('P', 'p', 'T', 't')) and (move.To.y == 0 or move.To.y == 4)
            
            if is_promo:
                is_check = MoveGenerator._move_causes_check(game, move)
                score = PROMO_CHECK_SCORE if is_check else PROMO_SCORE
                promotions.append((score, move, is_check))
                continue

            if to_piece != '.' or ((from_piece in ('P', 'p', 'T', 't')) and move.To == game.enPassantTarget):
                victim_char = to_piece if to_piece != '.' else ('p' if game.whiteToMove else 'P')
                victim = Agent._piece_to_points(victim_char)
                aggressor = Agent._piece_to_points(from_piece)
                mvv_lva_score = 10 * victim - aggressor
                
                if victim > aggressor:
                    score = GOOD_CAPTURE_BASE + mvv_lva_score
                    is_check = MoveGenerator._move_causes_check(game, move)
                    if is_check: score += CHECK_BONUS
                    good_captures.append((score, move, is_check))
                else:
                    score = BAD_CAPTURE_BASE + mvv_lva_score
                    bad_captures.append((score, move, None))
                continue

            # Quiet
            if reduced_move == k1:
                killers.append((2, move))
            elif reduced_move == k2:
                killers.append((1, move))
            else:
                is_check = MoveGenerator._move_causes_check(game, move)
                if is_check:
                    quiet_checks.append(move)
                else:
                    score = Agent.history_table[move.From.x][move.From.y][move.To.x][move.To.y]
                    history_moves.append((score, move))

        promotions.sort(reverse=True)
        for _, move, is_check in promotions: yield move, is_check
            
        good_captures.sort(reverse=True)
        for _, move, is_check in good_captures: yield move, is_check

        killers.sort(reverse=True)
        for _, move in killers: yield move, None
            
        for move in quiet_checks: yield move, True
            
        history_moves.sort(reverse=True)
        for _, move in history_moves: yield move, False
            
        bad_captures.sort(reverse=True)
        for _, move, is_check in bad_captures: yield move, is_check

    @staticmethod
    def _move_causes_check(game: GameState, move: PositionPair) -> bool:
        # Optimized check detection is hard without making the move.
        # Fallback to make-unmake or pseudo-detection.
        # Since 5x5 is small, we can quickly simulate on bitboards?
        # Actually, let's use the 'make move on copy' logic but lightweight.
        # The original code did complex raytracing.
        # Here we can just do:
        info = game._move(move.From, move.To)
        # Note: _move flips the turn. 
        # After _move, whiteToMove is opponent.
        # So we check if *opponent* (who just moved) attacks the King of the side that is now to move?
        # No, _move flips turn.
        # Start: White to move.
        # Make move.
        # End: Black to move.
        # Did White check Black?
        # We need to check if Black King is attacked by White.
        # In GameState._move, we calculate `IsLegal` by checking if White King is attacked by Black.
        
        # We want to know if the move *gives* check.
        # i.e. Is the ENEMY king attacked now?
        is_check = game._current_player_is_in_check() # Checks if side-to-move is in check
        game.undo_move(info)
        return is_check


# =============================================================================
# Agent.cs
# =============================================================================
class Agent:
    MAX_SEARCH_DEPTH = 64
    MAX_Q_DEPTH = 8
    
    killer_moves: List[List[Optional[ReducedMoveInfo]]] = [[None, None] for _ in range(MAX_SEARCH_DEPTH)]
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

    MemoEntry.Default = MemoEntry(0, 0, MemoEntryType.Exact, ReducedMoveInfo(Position.Null, Position.Null), False)
    memo = {}

    # FLATTENED PSTs (0..24)
    # Original were [y][x], mapped to 5*y + x.
    pst_pawn = [
         0,   0,   0,   0,   0,
         5,  10,  10,  10,   5,
        20,  30,  40,  30,  20,
        50,  70,  90,  70,  50,
         0,   0,   0,   0,   0
    ]
    pst_knight = [
        -20, -10, -10, -10, -20,
        -10,   5,  10,   5, -10,
        -10,  15,  30,  15, -10,
        -10,   5,  10,   5, -10,
        -20, -10, -10, -10, -20
    ]
    pst_bishop = [
        -10,  -5, -10,  -5, -10,
         -5,   5,   5,   5,  -5,
        -10,  10,  20,  10, -10,
         -5,   5,   5,   5,  -5,
        -10,  -5, -10,  -5, -10
    ]
    pst_queen = [
         -5,  -5,  -5,  -5,  -5,
         -5,   5,   5,   5,  -5,
         -5,  10,  15,  10,  -5,
         -5,   5,   5,   5,  -5,
         -5,  -5,  -5,  -5,  -5
    ]
    pst_right = [
        -15,  -5,  -5,  -5, -15,
         -5,   5,  10,   5,  -5,
         -5,  10,  20,  10,  -5,
         -5,   5,  10,   5,  -5,
        -15,  -5,  -5,  -5, -15
    ]
    pst_king_mg = [
         20,  30,  10,  30,  20,
         10,   0, -20,   0,  10,
        -20, -30, -50, -30, -20,
        -30, -40, -50, -40, -30,
        -50, -50, -50, -50, -50
    ]
    pst_king_eg = [
        -20, -10, -10, -10, -20,
        -10,  10,  20,  10, -10,
        -10,  20,  40,  20, -10,
        -10,  10,  20,  10, -10,
        -20, -10, -10, -10, -20
    ]

    @staticmethod
    def _piece_to_points(piece: str) -> int:
        if piece in ('P', 'p', 'T', 't'): return 100
        if piece in ('N', 'n', 'B', 'b'): return 300
        if piece in ('R', 'r'): return 600
        if piece in ('Q', 'q'): return 900
        return 0
    
    @staticmethod
    def _position_to_points(idx: int, piece: str, is_endgame: bool = False) -> int:
        # PSTs are defined for White perspective.
        # If piece is white, use idx.
        # If piece is black, we need to flip the board vertically?
        # Original code: y = position.y if piece.isupper() else 4 - position.y
        # y = idx // 5. x = idx % 5.
        y = idx // 5
        x = idx % 5
        if piece.islower():
            y = 4 - y
        
        table_idx = y * 5 + x
        
        p = piece.upper()
        if p == 'P' or p == 'T': return Agent.pst_pawn[table_idx]
        if p == 'N': return Agent.pst_knight[table_idx]
        if p == 'B': return Agent.pst_bishop[table_idx]
        if p == 'R': return Agent.pst_right[table_idx]
        if p == 'Q': return Agent.pst_queen[table_idx]
        if p == 'K': return Agent.pst_king_eg[table_idx] if is_endgame else Agent.pst_king_mg[table_idx]
        return 0
    
    @staticmethod
    def _heuristic(game: GameState) -> int:
        # Quick check for endgame via bitboards
        # Nuke check: Queen or Right
        is_endgame = True
        nuke_mask = game.bb_W_Q | game.bb_W_R if game.whiteToMove else game.bb_B_q | game.bb_B_r
        if nuke_mask: is_endgame = False
        
        heuristic = 0
        total_pieces = 0
        
        # Iterate all pieces efficiently
        temp = game.bb_All
        while temp:
            idx, temp = pop_lsb(temp)
            total_pieces += 1
            piece = game.get_piece_at_index(idx)
            is_for = game.piece_is_movers(piece)
            value = Agent._piece_to_points(piece) + Agent._position_to_points(idx, piece, is_endgame)
            heuristic += value if is_for else -value

        if heuristic > 0: heuristic -= total_pieces
        elif heuristic < 0: heuristic += total_pieces

        return heuristic

    @staticmethod
    def _negate(value: Optional[int]) -> Optional[int]:
        if value is not None:
            return -value
        return None

    @staticmethod
    def _quiescence(game: GameState, alpha: int, beta: int, ply: int, hash_val: int, q_depth: int, start_time: int, time_limit: int) -> Optional[int]:
        if time.perf_counter() - start_time > time_limit:
            return None

        if DrawDetector.is_drawn(hash_val):
            return 0

        q_search_tt_depth = 0 
        memo_entry = Agent.memo.get(hash_val, None)
        
        if memo_entry and memo_entry.Depth >= q_search_tt_depth:
            if memo_entry.Type == Agent.MemoEntryType.Exact: return memo_entry.Value
            elif memo_entry.Type == Agent.MemoEntryType.LowerBound: alpha = max(alpha, memo_entry.Value)
            elif memo_entry.Type == Agent.MemoEntryType.UpperBound: beta = min(beta, memo_entry.Value)
            if alpha >= beta: return memo_entry.Value

        if q_depth == 0:
            return Agent._heuristic(game)

        stand_pat_score = Agent._heuristic(game)
        if stand_pat_score >= beta:
            Agent.memo[hash_val] = Agent.MemoEntry(stand_pat_score, q_search_tt_depth, Agent.MemoEntryType.LowerBound, ReducedMoveInfo(Position.Null, Position.Null))
            return beta
        
        alpha = max(alpha, stand_pat_score)
        
        max_val = stand_pat_score
        initial_alpha = alpha
        best_move_info = ReducedMoveInfo(Position.Null, Position.Null)

        valid_memo_entry = memo_entry if memo_entry else Agent.MemoEntry.Default
        moves = MoveGenerator.generate_q_moves(game, valid_memo_entry)

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

            if value is None: return None

            if value > max_val:
                max_val = value
                best_move_info = info.to_reduced_move_info()

            alpha = max(alpha, value)
            if alpha >= beta:
                break
        
        memo_type = Agent.MemoEntryType.Exact
        if max_val <= initial_alpha: memo_type = Agent.MemoEntryType.UpperBound
        elif max_val >= beta: memo_type = Agent.MemoEntryType.LowerBound
        
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
            if memo_entry.Type == Agent.MemoEntryType.Exact: return memo_entry.Value
            elif memo_entry.Type == Agent.MemoEntryType.LowerBound: alpha = max(alpha, memo_entry.Value)
            elif memo_entry.Type == Agent.MemoEntryType.UpperBound: beta = min(beta, memo_entry.Value)
            if alpha >= beta: return memo_entry.Value
        
        if game.is_drawn_by_only_kings():
            return 0

        # Futility
        if (depth == 1 or depth == 2) and not in_check:
            static_eval = Agent._heuristic(game)
            futility_margin = 100 * (3 - depth)
            if static_eval + futility_margin < alpha:
                return Agent._quiescence(game, alpha, beta, ply, hash_val, Agent.MAX_Q_DEPTH, start_time, time_limit)

        # Null Move
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

            if value is None: return None
            if value >= beta: return beta 

        max_val = -1_000_000_000
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
                # Fallback to precise check detection if needed
                is_checking = MoveGenerator._move_causes_check(game, poistion_pair)
            
            move_index += 1
            new_hash = GameState.Zobrist.update_hash(hash_val, info)
            DrawDetector.do(new_hash)
            value = 0
                    
            if move_index == 1:
                value = Agent._negamax(game, -beta, -alpha, depth - 1, ply + 1, new_hash, start_time, time_limit, is_checking)
                value = Agent._negate(value)
            else:
                reduction = 0
                is_quiet = (info.ToPiece == '.' and not info.IsPromotion)
                if depth >= 3 and is_quiet and not is_checking:
                    reduction = int(0.5 + math.log(depth) * math.log(move_index) / 2.0)
                    reduction = max(0, reduction)
                    reduction = min(reduction, depth - 2)

                new_depth = depth - 1 - reduction
                value = Agent._negamax(game, -(alpha + 1), -alpha, new_depth, ply + 1, new_hash, start_time, time_limit, is_checking)
                value = Agent._negate(value)

                if value is not None and value > alpha and reduction > 0:
                    value = Agent._negamax(game, -beta, -alpha, depth - 1, ply + 1, new_hash, start_time, time_limit, is_checking)
                    value = Agent._negate(value)

            DrawDetector.undo(new_hash)
            game.undo_move(info)

            if value is None: return None

            if value > max_val:
                max_val = value
                best_move = info
                if info.ToPiece == '.' and not info.EPPiece == '.' and not info.IsPromotion:
                    Agent.history_table[info.From.x][info.From.y][info.To.x][info.To.y] += depth * depth
            
            alpha = max(alpha, value)
            if alpha >= beta:
                if info.ToPiece == '.' and not info.IsPromotion:
                    reduced_move = info.to_reduced_move_info()
                    if reduced_move != Agent.killer_moves[ply][0]:
                        Agent.killer_moves[ply][1] = Agent.killer_moves[ply][0]
                        Agent.killer_moves[ply][0] = reduced_move
                break
        
        if move_index == 0:
            return -(10_000 + depth)

        memo_type = Agent.MemoEntryType.Exact
        if max_val <= initial_alpha: memo_type = Agent.MemoEntryType.UpperBound
        elif max_val >= beta: memo_type = Agent.MemoEntryType.LowerBound
        
        if not memo_entry or depth >= memo_entry.Depth:
            Agent.memo[hash_val] = Agent.MemoEntry(max_val, depth, memo_type, best_move.to_reduced_move_info())

        return max_val

    @staticmethod
    def find_best_move(game: GameState, depth: int, start_time: int, time_limit: int, hash_val: int, alpha = -1_000_000_000, beta = 1_000_000_000) -> Optional[Tuple[MoveInfo, int]]:
        if time.perf_counter() - start_time > time_limit:
            return None
        
        max_val = -1_000_000_000
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

            if value is None: return None

            if value > max_val:
                best_move = info
                max_val = value

            alpha = max(alpha, value)
            if alpha >= beta:
                break

        return best_move, max_val


### == Here marks the end of the translated C# agent == ###
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
    
    pawn = piece
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
    return board_str + '\n' + str(DrawDetector.positions)


def agent(board, player, var):
    start_time = time.perf_counter()

    global state
    cm_board: CM_Board = board
    cm_player: CM_Player = player
    ply_id: int = var[0]
    timeout: float = var[1] - 1
    
    take_notes(f"=== Ply {ply_id} ({player}) ===")

    if ply_id <= 1:
        DrawDetector.positions.clear()
        Agent.memo.clear()
        Agent.killer_moves = [[None, None] for _ in range(Agent.MAX_SEARCH_DEPTH)]
        Agent.history_table = [[[[0 for _ in range(5)] for _ in range(5)] for _ in range(5)] for _ in range(5)]

    epTarget: CM_Position | None = None
    
    # We rebuild the state from scratch every turn to match the CM board
    state._clear_bitboards()
    
    for row in cm_board._squares:
        for square in row:
            piece: CM_Piece | None = square.piece
            position: CM_Position = square.position
            symbol = piece_to_symbol(piece)
            pos = to_cs_position(position)
            state[pos] = symbol # Use setter to update bitboards

            if epTarget is None:
                epTarget = find_en_passant_target(cm_board, piece)

            if symbol == 'K':
                state.whiteKing = pos
            elif symbol == 'k':
                state.blackKing = pos

    state.enPassantTarget = Position(epTarget.x, epTarget.y) if epTarget is not None else Position.Null
    state.whiteToMove = (cm_player.name == "white")

    best_move_so_far = None
    best_value = -1_000_000_000
    depth = 0

    hash_val = GameState.Zobrist.compute_hash(state)
    DrawDetector.do(hash_val)

    while True:
        depth += 1
        take_notes(f"Searching depth {depth}...")

        alpha = best_value - 25 
        beta = best_value + 25

        res = Agent.find_best_move(state, depth, start_time, timeout, hash_val, alpha, beta)
        if res is None:
            take_notes(f"Timeout imminent. Returning best move from depth {depth - 1}")
            break

        move, value = res

        if value <= alpha or value >= beta:
            take_notes(f"  Aspiration failed (a={alpha}, b={beta}, v={value}). Re-searching...")
            alpha = -1_000_000_000
            beta =  1_000_000_000
            res = Agent.find_best_move(state, depth, start_time, timeout, hash_val, alpha, beta)
            if res is None:
                take_notes(f"Timeout imminent. Returning best move from depth {depth - 1}")
                break
            move, value = res

        best_move_so_far = move
        best_value = value

        if value >= 10_000:
            take_notes(f"Found mate at depth {depth}!")
            break

    move = best_move_so_far
    value = best_value

    DrawDetector.do(GameState.Zobrist.update_hash(hash_val, move))
    
    take_notes(f"{player} moved from {move.From} to {move.To} with eval {value}")

    return find_move_on_cm_board(cm_board, move)