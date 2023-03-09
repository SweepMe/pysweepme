import socket

HOST = "127.0.0.1"  # localhost/loopback
PORT = 65432  # non-privileged ports are > 1023

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:

    server.bind((HOST, PORT))
    # server.settimeout(1)
    server.listen()

    cnxn, address = server.accept()
    with cnxn:
        print("Echo server connected")
        while True:
            data = cnxn.recv(1024)
            if not data:
                break
            cnxn.sendall(data)

# client example

# with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:

#     client.connect((HOST, PORT))
#     client.sendall(b"hello world ")
#     data = client.recv(1024)