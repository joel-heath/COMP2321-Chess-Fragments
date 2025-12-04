import sys
import time
import threading
import queue
import pygame
import copy
from itertools import cycle

# --- User Imports ---
from chessmaker.chess.base import Board
from extension.board_rules import get_result, THINKING_TIME_BUDGET, GAME_TIME_BUDGET
from samples import white, black, sample0
from agent import agent
from opponent import opponent

# --- Configuration ---
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 800

# 5x5 Board Settings
BOARD_DIM = 5
BOARD_PIXEL_SIZE = 600
SQUARE_SIZE = BOARD_PIXEL_SIZE // BOARD_DIM

OFFSET_X = (WINDOW_WIDTH - BOARD_PIXEL_SIZE) // 2
OFFSET_Y = (WINDOW_HEIGHT - BOARD_PIXEL_SIZE) // 2

# Colors
# 1. light squares #edd6b0 -> (237, 214, 176)
COLOR_LIGHT = (237, 214, 176)
# 2. dark squares #b88762 -> (184, 135, 98)
COLOR_DARK = (184, 135, 98)

# 3. light square yellowed #f6eb72 -> (246, 235, 114)
COLOR_LIGHT_HIGHLIGHT = (246, 235, 114)
# 4. dark square yellowed #dcc34b -> (220, 195, 75)
COLOR_DARK_HIGHLIGHT = (220, 195, 75)

COLOR_BG = (49, 46, 43)
COLOR_DOT = (100, 100, 100, 100) # Move hint dots
COLOR_TEXT = (255, 255, 255)
COLOR_BTN = (80, 80, 80)
COLOR_BTN_HOVER = (100, 100, 100)
COLOR_OVERLAY = (0, 0, 0, 200)

ASSET_PIECE_PATH = "assets/pieces/{}{}.png"
ASSET_SOUND_PATH = "assets/sounds/{}.mp3"

class ChessGame:
    def __init__(self):
        pygame.init()
        pygame.mixer.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("5x5 Python Chess")
        self.font = pygame.font.SysFont("Segoe UI", 28)
        self.font_big = pygame.font.SysFont("Segoe UI", 48)
        self.clock = pygame.time.Clock()

        self.images = {}
        self.sounds = {}
        self.load_assets()

        self.state = 'MENU'
        self.board = None
        self.players = []
        self.ply = 1
        
        self.mode = None         
        self.human_color = "white"
        self.agent_color = "white"
        self.view_flipped = False 

        self.selected_piece = None
        self.selected_pos = None 
        self.last_move = None # Stores tuple ((start_x, start_y), (end_x, end_y))
        self.legal_moves = []
        self.game_result_text = ""

        self.bot_queue = queue.Queue()
        self.is_thinking = False

    def load_assets(self):
        pieces = ['p', 'r', 'n', 'b', 'q', 'k']
        colors = ['w', 'b']
        for c in colors:
            for p in pieces:
                key = f"{c}{p}"
                try:
                    img = pygame.image.load(ASSET_PIECE_PATH.format(c, p))
                    self.images[key] = pygame.transform.scale(img, (SQUARE_SIZE, SQUARE_SIZE))
                except FileNotFoundError:
                    s = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE))
                    s.fill((255, 0, 0))
                    self.images[key] = s

        snd_map = {'move': 'move-self', 'opponent': 'move-opponent', 'check': 'move-check', 'promote': 'promote', 'capture': 'capture', 'end': 'game-end'}
        for k, v in snd_map.items():
            try:
                self.sounds[k] = pygame.mixer.Sound(ASSET_SOUND_PATH.format(v))
            except FileNotFoundError:
                pass

    def play_sound(self, name):
        if name in self.sounds: self.sounds[name].play()

    # --- Coordinates ---
    # Standard Vertical Chess View
    # x = Column (0..4)
    # y = Row (0..4)
    # y=0 is White (Bottom), y=4 is Black (Top)

    def to_screen_rect(self, lx, ly):
        """Converts Logical Board (lx, ly) to Screen Rect"""
        
        if not self.view_flipped:
            # White at Bottom
            sx = lx * SQUARE_SIZE
            sy = (BOARD_DIM - 1 - ly) * SQUARE_SIZE
        else:
            # Black at Bottom (Flipped)
            sx = (BOARD_DIM - 1 - lx) * SQUARE_SIZE
            sy = ly * SQUARE_SIZE
            
        return pygame.Rect(OFFSET_X + sx, OFFSET_Y + sy, SQUARE_SIZE, SQUARE_SIZE)

    def to_logical_pos(self, mx, my):
        """Mouse -> Logical (lx, ly)"""
        rel_x = mx - OFFSET_X
        rel_y = my - OFFSET_Y
        
        if rel_x < 0 or rel_y < 0 or rel_x >= BOARD_PIXEL_SIZE or rel_y >= BOARD_PIXEL_SIZE:
            return None

        col = rel_x // SQUARE_SIZE
        row = rel_y // SQUARE_SIZE

        if not self.view_flipped:
            # White Bottom
            lx = col
            ly = (BOARD_DIM - 1) - row
        else:
            # Black Bottom
            lx = (BOARD_DIM - 1) - col
            ly = row
            
        return (lx, ly)

    # --- Core Logic ---

    def start_game(self, mode):
        self.mode = mode
        
        # 1. DEEPCOPY to ensure fresh state
        squares_copy = copy.deepcopy(sample0)
        
        # 2. Extract the NEW player objects created by deepcopy
        # We cannot use the global 'white'/'black' because the pieces in 'squares_copy'
        # now belong to new player instances.
        p_white = None
        p_black = None
        
        # Hunt for the player objects in the board squares
        for row in squares_copy:
            for sq in row:
                if sq.piece:
                    if sq.piece.player.name == "white":
                        p_white = sq.piece.player
                    elif sq.piece.player.name == "black":
                        p_black = sq.piece.player
        
        # Fallback if board is empty (unlikely)
        # if not p_white: p_white = copy.deepcopy(white)
        # if not p_black: p_black = copy.deepcopy(black)
        
        self.players = [p_white, p_black]
        
        # 3. Create Board
        self.board = Board(
            squares=squares_copy,
            players=self.players,
            turn_iterator=cycle(self.players)
        )

        self.ply = 1
        self.state = 'GAME'
        self.game_result_text = ""
        self.selected_piece = None
        self.last_move = None
        self.legal_moves = []
        self.is_thinking = False
        
        # Auto-flip view based on Human Color
        if mode == 'HvB' and self.human_color == 'black':
            self.view_flipped = True 
        else:
            self.view_flipped = False

    def get_piece(self, x, y):
        # x = Logical Column (0..4)
        # y = Logical Row (0 is Bottom, 4 is Top)

        # 1. Fix Rotation: Access array as [row][col] instead of [x][y]
        # 2. Fix Inversion: Map Logical Y (0=Bottom) to Array Index (0=Top)
        row_index = (BOARD_DIM - 1) - y
        col_index = x

        try:
            return self.board._squares[row_index][col_index].piece
        except (IndexError, AttributeError):
            return None

    def execute_move(self, piece, move_opt):
        def in_check():
            from chessmaker.chess.pieces import King
            kings = [piece for piece in self.board.get_player_pieces(self.board.current_player) if isinstance(piece, King)]
            return any(king.is_attacked() for king in kings)

        try:
            # 5.1 & 5.2 Store move info for highlighting before executing
            # Convert Array coordinates (0=Top) to Logical coordinates (0=Bottom)
            start_pos = (piece.position.x, BOARD_DIM - 1 - piece.position.y)
            end_pos = (move_opt.position.x, BOARD_DIM - 1 - move_opt.position.y)
            self.last_move = (start_pos, end_pos)

            piece.move(move_opt)
            self.ply += 1
            
            # Sound
            
            if in_check():
                self.play_sound('check')
            elif hasattr(move_opt, "extra") and move_opt.extra and "promote" in move_opt.extra: # extra=dict(promote=promotion_name)
                self.play_sound('promote')
            elif hasattr(move_opt, "captures") and move_opt.captures:
                self.play_sound('capture')
            else:
                is_white = (self.board.current_player.name == "white")
                if is_white: self.play_sound('move')
                else: self.play_sound('opponent')

            # Check Result
            res = get_result(self.board)
            if res:
                self.game_result_text = f"{res}"
                self.play_sound('end')
                self.state = 'GAMEOVER'
            
            # Clear selection state (whether game over or not) to hide move options
            self.selected_piece = None
            self.legal_moves = []
                
        except Exception as e:
            print(f"Move Error: {e}")
            import traceback
            traceback.print_exc()

    # --- Bot Threading ---

    def bot_worker(self, bot_func, board_copy, player, var_data):
        try:
            p, m = bot_func(board_copy, player, var_data)
            self.bot_queue.put((p, m))
        except Exception as e:
            print(f"Bot crash detected: {e}")
            self.bot_queue.put(None)

    def trigger_bot(self):
        if self.is_thinking: return
        
        bot_func = None
        if self.mode == 'HvB':
            bot_func = agent
        elif self.mode == 'BvB':
            bot_func = agent if self.board.current_player.name == self.agent_color else opponent

        if bot_func:
            self.is_thinking = True
            
            try:
                board_clone = self.board.clone()
                
                # Match current player to clone's player
                clone_player = None
                for p in board_clone.players:
                    if p.name == self.board.current_player.name:
                        clone_player = p
                        break
                
                if not clone_player:
                    # Fallback
                    clone_player = board_clone.players[0] if board_clone.players[0].name == self.board.current_player.name else board_clone.players[1]

                t = threading.Thread(target=self.bot_worker, args=(
                    bot_func, 
                    board_clone, 
                    clone_player, 
                    [self.ply, THINKING_TIME_BUDGET]
                ))
                t.daemon = True
                t.start()
            except Exception as e:
                print(f"Failed to start bot thread: {e}")
                self.is_thinking = False

    def update_bot(self):
        try:
            data = self.bot_queue.get_nowait()
            self.is_thinking = False
            
            if data:
                res_piece, res_move = data
                if res_piece is None or res_move is None:
                    return

                # Map clone -> real board
                real_piece = None
                
                for x in range(BOARD_DIM):
                    for y in range(BOARD_DIM):
                        p = self.get_piece(x, y)
                        # Match by position
                        if p and p.position.x == res_piece.position.x and p.position.y == res_piece.position.y:
                            real_piece = p
                            break
                    if real_piece: break
                
                if real_piece:
                    real_move = None
                    for m in real_piece.get_move_options():
                        if m.position.x == res_move.position.x and m.position.y == res_move.position.y:
                            real_move = m
                            break
                    if real_move:
                        self.execute_move(real_piece, real_move)
                        
        except queue.Empty:
            pass

    # --- Rendering ---

    def draw_text_centered(self, text, y_pos, color=COLOR_TEXT, font=None):
        if not font: font = self.font
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=(WINDOW_WIDTH//2, y_pos))
        self.screen.blit(surf, rect)

    def draw_btn(self, rect, text, hover=False):
        c = COLOR_BTN_HOVER if hover else COLOR_BTN
        pygame.draw.rect(self.screen, c, rect, border_radius=8)
        pygame.draw.rect(self.screen, (200,200,200), rect, 2, border_radius=8)
        surf = self.font.render(text, True, COLOR_TEXT)
        txt_rect = surf.get_rect(center=rect.center)
        self.screen.blit(surf, txt_rect)

    def draw_menu(self):
        self.screen.fill(COLOR_BG)
        self.draw_text_centered("Chess Main Menu", 150, font=self.font_big)
        
        mx, my = pygame.mouse.get_pos()
        btns = [
            ("Human vs Human", 300, "HvH"),
            ("Human vs Bot", 380, "HvB"),
            ("Bot vs Bot", 460, "BvB")
        ]
        
        self.menu_rects = {}
        for label, y, mode in btns:
            r = pygame.Rect(0, 0, 300, 60)
            r.center = (WINDOW_WIDTH//2, y)
            is_hover = r.collidepoint((mx, my))
            self.draw_btn(r, label, is_hover)
            self.menu_rects[mode] = r

        self.draw_text_centered(f"Play as: {self.human_color.title()}", 600)
        col_btn = pygame.Rect(0, 0, 200, 40)
        col_btn.center = (WINDOW_WIDTH//2, 640)
        self.draw_btn(col_btn, "Swap Color", col_btn.collidepoint((mx,my)))
        self.menu_rects["swap_c"] = col_btn

    def draw_game_ui(self):
        ui_x = OFFSET_X + BOARD_PIXEL_SIZE + 20
        pygame.draw.line(self.screen, (100,100,100), (ui_x-10, 50), (ui_x-10, WINDOW_HEIGHT-50))
        
        t_name = "White" if self.board.current_player.name == "white" else "Black"
        lbl = f"Turn: {t_name}"
        if self.is_thinking: lbl += " (Thinking...)"
        
        surf = self.font.render(lbl, True, COLOR_TEXT)
        self.screen.blit(surf, (ui_x, 50))
        
        mx, my = pygame.mouse.get_pos()
        flip_btn = pygame.Rect(ui_x, 150, 180, 50)
        self.draw_btn(flip_btn, "Flip View", flip_btn.collidepoint((mx, my)))
        self.game_ui_rects = {"flip": flip_btn}
        
        mm_btn = pygame.Rect(ui_x, WINDOW_HEIGHT - 100, 180, 50)
        self.draw_btn(mm_btn, "Exit to Menu", mm_btn.collidepoint((mx, my)))
        self.game_ui_rects["exit"] = mm_btn

    def draw_board(self):
        # Draw Squares
        for x in range(BOARD_DIM):
            for y in range(BOARD_DIM):
                rect = self.to_screen_rect(x, y)
                
                # Determine Base color and if it should be highlighted (yellowed)
                is_light_sq = ((x + y) % 2 == 0)
                should_highlight = False

                # 5.1 & 5.2 Highlight last move (start and end pos)
                if self.last_move:
                    start_p, end_p = self.last_move
                    if (x, y) == start_p or (x, y) == end_p:
                        should_highlight = True
                
                # 5.3 Highlight currently selected piece
                if self.selected_pos == (x, y):
                    should_highlight = True

                # Apply colors
                if is_light_sq:
                    color = COLOR_LIGHT_HIGHLIGHT if should_highlight else COLOR_LIGHT
                else:
                    color = COLOR_DARK_HIGHLIGHT if should_highlight else COLOR_DARK

                pygame.draw.rect(self.screen, color, rect)

        # Draw Pieces
        for x in range(BOARD_DIM):
            for y in range(BOARD_DIM):
                piece = self.get_piece(x, y)
                if piece:
                    rect = self.to_screen_rect(x, y)
                    
                    is_white = (piece.player.name == 'white')
                    char_color = 'w' if is_white else 'b'
                    
                    type_map = {'Knight': 'n', 'King': 'k', 'Queen': 'q', 'Right': 'r', 'Bishop': 'b', 'Pawn': 'p'}
                    p_name = piece.__class__.__name__
                    char_type = type_map.get(p_name, 'p')
                    
                    key = f"{char_color}{char_type}"
                    if key in self.images:
                        self.screen.blit(self.images[key], rect.topleft)
                    else:
                        txt = self.font.render(key, True, (0,0,0))
                        self.screen.blit(txt, rect.move(10,10))

        # Draw Moves hints
        if self.selected_piece and self.legal_moves:
            for move in self.legal_moves:
                mx = move.position.x
                my = 4 - move.position.y
                rect = self.to_screen_rect(mx, my)
                
                target_piece = self.get_piece(mx, my)
                
                if target_piece:
                    pygame.draw.circle(self.screen, (100,100,100), rect.center, SQUARE_SIZE//2 - 4, 6)
                else:
                    s = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
                    pygame.draw.circle(s, COLOR_DOT, (SQUARE_SIZE//2, SQUARE_SIZE//2), SQUARE_SIZE//6)
                    self.screen.blit(s, rect.topleft)

    def draw_gameover(self):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill(COLOR_OVERLAY)
        self.screen.blit(overlay, (0,0))
        
        self.draw_text_centered("GAME OVER", 300, font=self.font_big)
        self.draw_text_centered(self.game_result_text, 380)
        
        mx, my = pygame.mouse.get_pos()
        btn = pygame.Rect(0, 0, 250, 60)
        btn.center = (WINDOW_WIDTH//2, 500)
        self.draw_btn(btn, "Back to Menu", btn.collidepoint((mx, my)))
        self.gameover_rect = btn

    # --- Interaction Handlers ---

    def handle_click_menu(self, pos):
        for mode, rect in self.menu_rects.items():
            if rect.collidepoint(pos):
                if mode == "swap_c":
                    self.human_color = "black" if self.human_color == "white" else "white"
                else:
                    self.start_game(mode)

    def handle_click_game(self, pos):
        if "flip" in self.game_ui_rects and self.game_ui_rects["flip"].collidepoint(pos):
            self.view_flipped = not self.view_flipped
            return
        if "exit" in self.game_ui_rects and self.game_ui_rects["exit"].collidepoint(pos):
            self.state = 'MENU'
            return

        if self.is_thinking: return
        
        is_my_turn = False
        if self.mode == 'HvH': is_my_turn = True
        elif self.mode == 'HvB':
            if self.board.current_player.name == self.human_color: is_my_turn = True
        
        if not is_my_turn: return

        coords = self.to_logical_pos(pos[0], pos[1])
        if not coords:
            self.selected_piece = None
            self.selected_pos = None
            self.legal_moves = []
            return
        
        lx, ly = coords
        
        chosen_move = None
        for m in self.legal_moves:
            if m.position.x == lx and 4 - m.position.y == ly:
                chosen_move = m
                break
        
        if chosen_move:
            self.execute_move(self.selected_piece, chosen_move)
            return
            
        piece = self.get_piece(lx, ly)
        if piece and piece.player == self.board.current_player:
            self.selected_piece = piece
            self.selected_pos = (lx, ly)
            self.legal_moves = piece.get_move_options()
        else:
            self.selected_piece = None
            self.selected_pos = None
            self.legal_moves = []

    def handle_click_gameover(self, pos):
        if self.gameover_rect.collidepoint(pos):
            self.state = 'MENU'

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if self.state == 'MENU': self.handle_click_menu(event.pos)
                        elif self.state == 'GAME': self.handle_click_game(event.pos)
                        elif self.state == 'GAMEOVER': self.handle_click_gameover(event.pos)
                            
            if self.state == 'GAME':
                self.update_bot()
                
                should_bot_go = False
                if self.mode == 'BvB': should_bot_go = True
                elif self.mode == 'HvB' and self.board.current_player.name != self.human_color:
                    should_bot_go = True
                
                if should_bot_go and not self.game_result_text:
                    self.trigger_bot()

            self.screen.fill(COLOR_BG)
            if self.state == 'MENU': self.draw_menu()
            elif self.state == 'GAME': 
                self.draw_board()
                self.draw_game_ui()
            elif self.state == 'GAMEOVER':
                self.draw_board() 
                self.draw_gameover()
            
            pygame.display.flip()
            self.clock.tick(60)
            
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = ChessGame()
    game.run()