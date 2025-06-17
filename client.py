import socket, ssl

host = '192.168.134.188'  # Change if server IP is different
port = 5555

context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

with socket.create_connection((host, port)) as sock:
    with context.wrap_socket(sock, server_hostname=host) as ssock:
        name = input("Enter your name: ").strip()
        ssock.send(name.encode())

        while True:
            data = ssock.recv(4096).decode()
            if not data:
                break
            print(data, end="")

            if any(prompt in data.lower() for prompt in ["your turn", "yes/no", "enter your name"]):
                msg = input().strip()
                ssock.send(msg.encode())
