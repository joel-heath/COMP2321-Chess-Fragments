from cProfile import Profile
from pstats import SortKey, Stats

def profile_agent(agent_function, board, player, var):
    profiler = Profile()
    profiler.enable()
    
    result = agent_function(board, player, var)
    
    profiler.disable()
    stats = (Stats(profiler)
        .strip_dirs()
        .sort_stats(SortKey.CUMULATIVE) # or SortKey.CALLS
    )
    stats.print_stats()

    return result

import time
def time_agent(agent_function, board, player, var):
    start_time = time.perf_counter()
    agent_function(board, player, var)
    end_time = time.perf_counter()
    total_time = end_time - start_time
    print(f"{total_time:.6f} seconds")
    return total_time

from agent import agent
from samples import sample0
from test_fullgame import make_custom_board

if __name__ == "__main__":
    board, players = make_custom_board(sample0)
    player = players[0]
    var = [1, 40]  # [ply, thinking_time_budget]

    time_agent(agent, board, player, var)
    # profile_agent(agent, board, player, var)

# measured in seconds

#       |              chessmaker              |                      cs                         |
# depth |       DFS | zobrist, PVS |    undoer |      init | faster check detect | no mate check |
# ------|-----------|--------------|-----------|-----------|---------------------|---------------|
#     1 |  0.025014 |     0.027039 |  0.010901 |           |                     |               |
#     2 |  0.220387 |     0.225629 |  0.118735 |           |                     |               |
#     3 |  1.242618 |     0.657060 |  0.285701 |           |                     |               |
#     4 |  5.039525 |     3.999219 |  1.849807 |  0.711245 |                     |               |
#     5 | 13.115289 |    11.208792 |  4.967710 |  2.423873 |            1.125391 |               |
#     6 | 94.537617 |    31.993133 | 21.388204 |  8.576074 |            4.184340 |      0.985285 |
#     7 |           |              |           | 24.099357 |           12.051640 |      2.791586 |
#     8 |           |              |           |           |                     |     11.774208 |

# undoer IDS:
# Completed depth 1 (value = 0, time = 0.010992) 
# Completed depth 2 (value = -1, time = 0.148838) 
# Completed depth 3 (value = 0, time = 0.492116) 
# Completed depth 4 (value = 0, time = 2.629968) 
# Completed depth 5 (value = 1, time = 7.964976) 
# Completed depth 6 (value = -1, time = 31.295441)


# cs:
# Player (white) moved from a2 (P) to a3 (.) with eval 1 | 24.099357 seconds