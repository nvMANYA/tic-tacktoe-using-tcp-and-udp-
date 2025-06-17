import socket, threading, ssl
import traceback

class GameRoom:
    def _init_(self, room_id):
        self.room_id = room_id
        self.board = [" "] * 9
        self.players = {}
        self.player_names = {}
        self.scores = {"X": 0, "O": 0}
        self.current_player = "X"
        self.game_active = False
        self.lock = threading.Lock()
        self.play_again_responses = {}

    def add_player(self, player_socket):
        with self.lock:
            symbol = "X" if "X" not in self.players else "O"
            self.players[symbol] = player_socket

            player_socket.send("Enter your name: ".encode())
            name = player_socket.recv(1024).decode().strip()
            self.player_names[symbol] = name
            self.scores[symbol] = 0

            player_socket.send(f"You are Player {symbol} ({name}) in Room {self.room_id}\n".encode())

            if len(self.players) == 2:
                self.reset_board()
                self.game_active = True
                self.broadcast("\n🎮 Both players connected! Game is starting...\n")
                self.send_leaderboard()
                self.broadcast(self.print_board())
                self.players[self.current_player].send("Your turn! Enter position (0-8): ".encode())

            return symbol

    def broadcast(self, message, exclude=None):
        for s, sock in self.players.items():
            if sock != exclude:
                try:
                    sock.send(message.encode())
                except:
                    pass

    def print_board(self):
        b = self.board
        return (
            f"\n {b[0]} | {b[1]} | {b[2]} \n"
            "---+---+---\n"
            f" {b[3]} | {b[4]} | {b[5]} \n"
            "---+---+---\n"
            f" {b[6]} | {b[7]} | {b[8]} \n"
        )

    def check_winner(self):
        wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        for a, b, c in wins:
            if self.board[a] == self.board[b] == self.board[c] != " ":
                return self.board[a]
        return None

    def reset_board(self):
        self.board = [" "] * 9
        self.current_player = "X"

    def reset_game(self):
        self.reset_board()
        self.game_active = True
        self.play_again_responses.clear()
        self.broadcast("\n🔄 New round starting...\n")
        self.send_leaderboard()
        self.broadcast(self.print_board())
        self.players[self.current_player].send("Your turn! Enter position (0-8): ".encode())

    def send_leaderboard(self):
        leaderboard = "\n🏆 Leaderboard:\n"
        for symbol in ["X", "O"]:
            name = self.player_names.get(symbol, "Unknown")
            score = self.scores.get(symbol, 0)
            leaderboard += f"Player {symbol} ({name}): {score} points\n"
        self.broadcast(leaderboard)

class GameServer:
    def _init_(self):
        self.rooms = {}
        self.room_counter = 1
        self.lock = threading.Lock()

    def start(self, host='192.168.134.188', port=5555):
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.load_cert_chain('cert.pem', 'key.pem')

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen(5)
        print(f"[✅] Server started at {host}:{port} with SSL")

        while True:
            client, addr = server_socket.accept()
            secure_socket = context.wrap_socket(client, server_side=True)
            print(f"[+] Connection from {addr}")
            threading.Thread(target=self.handle_client, args=(secure_socket,)).start()

    def handle_client(self, client_socket):
        room = None
        symbol = None

        try:
            with self.lock:
                for r in self.rooms.values():
                    if len(r.players) == 1 and not r.game_active:
                        room = r
                        break
                if not room:
                    room = GameRoom(self.room_counter)
                    self.rooms[self.room_counter] = room
                    self.room_counter += 1

            symbol = room.add_player(client_socket)

            while True:
                data = client_socket.recv(1024).decode().strip()
                print(f"[{symbol}] Received input: {data}")  # Debug log

                if not data:
                    break

                with room.lock:
                    if not room.game_active:
                        if data.lower() in ["yes", "no"]:
                            room.play_again_responses[symbol] = data.lower()

                            if len(room.play_again_responses) == 2:
                                if all(v == "yes" for v in room.play_again_responses.values()):
                                    room.reset_game()
                                else:
                                    for s, response in room.play_again_responses.items():
                                        if response == "no":
                                            try:
                                                room.players[s].send("👋 You chose to exit.\n".encode())
                                                room.players[s].close()
                                                del room.players[s]
                                            except:
                                                pass
                                    room.play_again_responses.clear()
                                    room.game_active = False
                                    room.broadcast("🕓 Waiting for a new player to join...\n")
                        else:
                            client_socket.send("Please respond with 'yes' or 'no': ".encode())
                        continue

                    # ✅ VALIDATION: Ensure move is a number between 0 and 8
                    try:
                        move = int(data)
                        if move < 0 or move > 8:
                            client_socket.send("❌ Invalid input. Please enter a number between 0 and 8.\nYour turn! Enter position (0-8): ".encode())
                            continue
                    except ValueError:
                        client_socket.send("❌ Invalid input. Please enter a number between 0 and 8.\nYour turn! Enter position (0-8): ".encode())
                        continue

                    if room.board[move] != " ":
                        client_socket.send("❌ That cell is already taken. Try another.\nYour turn! Enter position (0-8): ".encode())
                    elif symbol != room.current_player:
                        client_socket.send("⏳ Not your turn! Wait for the other player.\n".encode())
                    else:
                        room.board[move] = symbol
                        winner = room.check_winner()
                        if winner:
                            room.broadcast(room.print_board())
                            room.broadcast(f"\n🏆 Player {winner} wins!\n")
                            room.scores[winner] += 1
                            room.game_active = False
                            room.send_leaderboard()
                            room.broadcast("🔁 Play again? (yes/no): ")
                        elif " " not in room.board:
                            room.broadcast(room.print_board())
                            room.broadcast("\n🤝 It's a draw!\n")
                            room.game_active = False
                            room.broadcast("🔁 Play again? (yes/no): ")
                        else:
                            room.current_player = "O" if room.current_player == "X" else "X"
                            room.broadcast(room.print_board())
                            room.players[room.current_player].send("Your turn! Enter position (0-8): ".encode())

        except Exception as e:
            print(f"[❌] Error: {e}")
            traceback.print_exc()
        finally:
            with self.lock:
                if room and symbol in room.players:
                    del room.players[symbol]
                if room and not room.players:
                    del self.rooms[room.room_id]
            client_socket.close()

if _name_ == "_main_":
    GameServer().start()
