"""Single-recipient SMTP submission. Called only after durable Owner approval and send gate."""
import smtplib,ssl
from email.message import EmailMessage
FROM_EMAIL='leo@etexpous.com'
FROM_NAME='ET EXPO / Leo'

def submit(config,draft):
 if config.get('from_email')!=FROM_EMAIL:raise ValueError('Approved sender mismatch')
 host=config.get('host','');port=int(config.get('port',465));mode=config.get('tls','ssl')
 if not host or mode not in {'ssl','starttls'} or port not in {465,587}:raise ValueError('Approved TLS SMTP configuration required')
 message=EmailMessage();message['From']=f'{FROM_NAME} <{FROM_EMAIL}>';message['To']=draft['to'];message['Subject']=draft['subject'];message['Message-ID']=draft['message_id'];message['Reply-To']=FROM_EMAIL
 message.set_content(draft['body'])
 client=smtplib.SMTP_SSL(host,port,timeout=20,context=ssl.create_default_context()) if mode=='ssl' else smtplib.SMTP(host,port,timeout=20)
 with client:
  if mode=='starttls':client.ehlo();client.starttls(context=ssl.create_default_context());client.ehlo()
  client.login(config['username'],config['password'])
  refused=client.send_message(message,from_addr=FROM_EMAIL,to_addrs=[draft['to']])
  if refused:raise RuntimeError('Recipient not accepted')
 return {'delivery_status':'SMTP_ACCEPTED','message_id':draft['message_id']}
