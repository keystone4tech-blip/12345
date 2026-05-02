import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('31.13.208.149', username='root', password='SuperNatural24!')

cmd = 'docker exec remnawave_bot wget -q -S -O - http://localhost:8080/health'
print(f"--- Running: {cmd} ---")
stdin, stdout, stderr = client.exec_command(cmd)
print("STDOUT:", stdout.read().decode('utf-8', errors='replace').strip())
print("STDERR:", stderr.read().decode('utf-8', errors='replace').strip())

client.close()
