import random
from extension.board_utils import list_legal_moves_for
from agent import agent

# Add your sequence of moves here
SCRIPTED_MOVES = [
    ("e2", "e4")
]

# Tracks progress through the list
SCRIPT_INDEX = 0

# ==========================================
#          Opponent Function
# ==========================================
from chessmaker.chess.base import Board, Player, Piece, MoveOption, Position

def scripted_opponent(board: Board, player: Player, var: list[int]) -> tuple[Piece, MoveOption]:
    global SCRIPT_INDEX

    if SCRIPT_INDEX >= len(SCRIPTED_MOVES):
        raise IndexError("Opponent Error: End of scripted move list reached.")

    target_from, target_to = SCRIPTED_MOVES[SCRIPT_INDEX]
    SCRIPT_INDEX += 1

    # Helper to convert CM_Position to "a1" string
    def pos_to_str(pos: Position) -> str:
        return f"{chr(ord('a') + pos.x)}{5 - pos.y}"

    # Search for the piece and move on the actual board
    for piece in board.get_player_pieces(player):
        
        # Check if piece is on the source square
        if pos_to_str(piece.position) == target_from:
            
            # Check the piece's legal moves
            for move_opt in piece.get_move_options():
                if pos_to_str(move_opt.position) == target_to:
                    print(f"[Opponent] Playing {target_from} -> {target_to}")
                    return piece, move_opt

    # If code reaches here, the move was not valid or the piece wasn't found
    raise ValueError(f"Opponent Error: Could not find valid move for {target_from} -> {target_to} on current board.")

def real_opponent(board, player, var):
    target_from = input("Enter the position of the piece you want to move (e.g., e2): ")
    target_to = input("Enter the position you want to move to (e.g., e4): ")

    # Helper to convert CM_Position to "a1" string
    def pos_to_str(pos: Position) -> str:
        return f"{chr(ord('a') + pos.x)}{5 - pos.y}"
    # Search for the piece and move on the actual board
    for piece in board.get_player_pieces(player):
        
        # Check if piece is on the source square
        if pos_to_str(piece.position) == target_from:
            
            # Check the piece's legal moves
            for move_opt in piece.get_move_options():
                if pos_to_str(move_opt.position) == target_to:
                    print(f"[Opponent] Playing {target_from} -> {target_to}")
                    return piece, move_opt
    # If code reaches here, the move was not valid or the piece wasn't found
    raise ValueError(f"Opponent Error: Could not find valid move for {target_from} -> {target_to} on current board.")

def deterministic_opponent(board, player, var):
    return list_legal_moves_for(board, player)[0]

def opponent(board, player, var):
    # return deterministic_opponent(board, player, var)
    # return agent(board, player, var)
    # return scripted_opponent(board, player, var)
    # return real_opponent(board, player, var)

    """
    This is an example of an random-move Opponent

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
    - Name of the player assigned to the Opponent (either "white" or "black"): player.name
    - list of pieces of the current player: list(board.get_player_pieces(player))
    - List of pieces and corresponding moves for each pieces of the player: piece, move_opt = list_legal_moves_for(board, player)
    - From var: ply = var[0], timeout = var[1]
    - Use the timeout variable together with time.perf_counter()
    to ensure the it returns its best move before the time limit expires.
    """
    piece, move_opt = None, None
    print(f"Ply: {var[0]}")

    if player.name == "white":

        while not move_opt:
            piece = random.choice(list(board.get_player_pieces(player)))
            mov = piece.get_move_options()
            if mov:
                move_opt = random.choice(mov)
                break
    else:
       
        while not move_opt:
            piece = random.choice(list(board.get_player_pieces(player)))
            mov = piece.get_move_options()
            if mov:
                move_opt = random.choice(mov)
                break

    return piece, move_opt
