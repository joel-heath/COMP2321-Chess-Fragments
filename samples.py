from chessmaker.chess.base import Player
from chessmaker.chess.pieces import King, Bishop, Knight, Queen
from extension.piece_right import Right
from extension.piece_pawn import Pawn_Q
from chessmaker.chess.base import Square

white = Player("white")
black = Player("black")

sample0 = [
        [Square(Knight(black)), Square(Queen(black)), Square(King(black)), Square(Bishop(black)), Square(Right(black))],
        [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)),Square(Pawn_Q(black))],
        [Square(), Square(), Square(), Square(),Square()],
        [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)),Square(Pawn_Q(white))],
        [Square(Right(white)), Square(Bishop(white)),  Square(King(white)), Square(Queen(white)), Square(Knight(white))],
        ]

sample1 = [
        [Square(Right(black)), Square(Queen(black)), Square(King(black)), Square(Knight(black)), Square(Bishop(black))],
        [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)),Square(Pawn_Q(black))],
        [Square(), Square(), Square(), Square(),Square()],
        [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)),Square(Pawn_Q(white))],
        [Square(Bishop(white)), Square(Knight(white)),  Square(King(white)), Square(Queen(white)), Square(Right(white))],
        ]


# === My Additions Below ===

PIECE_MAP = {
    'n': lambda: Square(Knight(black)),
    'q': lambda: Square(Queen(black)),
    'k': lambda: Square(King(black)),
    'b': lambda: Square(Bishop(black)),
    'r': lambda: Square(Right(black)),
    'p': lambda: Square(Pawn_Q(black)),
    
    'N': lambda: Square(Knight(white)),
    'Q': lambda: Square(Queen(white)),
    'K': lambda: Square(King(white)),
    'B': lambda: Square(Bishop(white)),
    'R': lambda: Square(Right(white)),
    'P': lambda: Square(Pawn_Q(white)),
    
    '.': lambda: Square(),
}

def parse_board_string(board_string: str) -> list[list[Square]]:
    """
    Parses a multi-line string representation of a board
    into a 2D list of Square objects.
    """
    board = []
    lines = board_string.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        parts = line.split()
        
        if parts and len(parts) > 1 and parts[0].isdigit() and not parts[1].isdigit():
            row_chars = parts[1:]
            
            row = []
            for char in row_chars:
                if char in PIECE_MAP:
                    row.append(PIECE_MAP[char]())
                else:
                    raise Exception(f"Unknown character '{char}' encountered.")
            
            if row:
                board.append(row)
                
    return board


game1 = parse_board_string("""
  0 1 2 3 4
0 n q k b r
1 . p . . p
2 . . . . .
3 . P . . P
4 N Q K B R""")

game3 = parse_board_string("""
  0 1 2 3 4
0 n q k b r
1 p p p p p
2 . . . . .
3 P P P P P
4 N Q K B R""")