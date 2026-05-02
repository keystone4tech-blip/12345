import paramiko
import sys

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('31.13.208.149', username='root', password='SuperNatural24!')

stdin, stdout, stderr = client.exec_command('cd /opt/mozhnovpn && docker logs remnawave_bot --tail 50')
with open('bot_logs.txt', 'w', encoding='utf-8') as f:
    f.write("STDOUT:\n")
    f.write(stdout.read().decode('utf-8', errors='replace'))
    f.write("\nSTDERR:\n")
    f.write(stderr.read().decode('utf-8', errors='replace'))

client.close()
