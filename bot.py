from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError, UserBlockedError, InputUserDeactivatedError
from pymongo import MongoClient
from flask import Flask, request
import asyncio
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB setup
mongo_uri = os.getenv('MONGO_URI')
client = MongoClient(mongo_uri)
db = client['bot_database']
users_collection = db['users']

# Telegram API credentials
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
PORT = int(os.getenv('PORT', 5000))  # Default port is 5000

# Create the client and connect
bot = TelegramClient('bot_pinterest', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Create a Flask app
app = Flask(__name__)

async def full_userbase():
    return [user['user_id'] for user in users_collection.find()]

async def del_user(user_id):
    users_collection.delete_one({'user_id': user_id})

async def send_text(client, event, admins):
    if event.sender_id in admins:
        if hasattr(event.message, 'reply_to') and event.message.reply_to:
            query = await full_userbase()
            broadcast_msg = await event.message.get_reply_message()
            total = 0
            successful = 0
            blocked = 0
            deleted = 0
            unsuccessful = 0

            pls_wait = await event.reply("<i>Broadcasting Message.. This will Take Some Time</i>", parse_mode='html')
            for chat_id in query:
                try:
                    await client.send_message(chat_id, broadcast_msg.text)
                    successful += 1
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                    await client.send_message(chat_id, broadcast_msg.text)
                    successful += 1
                except UserBlockedError:
                    await del_user(chat_id)
                    blocked += 1
                except InputUserDeactivatedError:
                    await del_user(chat_id)
                    deleted += 1
                except Exception as e:
                    unsuccessful += 1
                    logger.error(f"Failed to send message to {chat_id}: {e}")
                total += 1

            status = (
                f"<b><u>Broadcast Completed</u></b>\n\n"
                f"📋 <b>Total Users:</b> <code>{total}</code>\n\n"
                f"✅ <b>Successful:</b> <code>{successful}</code>\n\n"
                f"🚫 <b>Blocked Users:</b> <code>{blocked}</code>\n\n"
                f"🗑️ <b>Deleted Accounts:</b> <code>{deleted}</code>\n\n"
                f"❌ <b>Unsuccessful:</b> <code>{unsuccessful}</code>\n"
            )

            await pls_wait.edit(status, parse_mode='html')
        else:
            await event.reply("Please reply to a message to broadcast.")
    else:
        await event.reply("You are not authorized to use this command.")

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    try:
        user_id = event.sender_id
        username = (await bot.get_entity(user_id)).username or "Anonymous"
        
        # Store user in MongoDB
        users_collection.update_one(
            {'user_id': user_id},
            {'$set': {'username': username}},
            upsert=True
        )
        
        # Send welcome message with buttons
        await event.respond(
            f"Welcome, {username}!",
            buttons=[
                [Button.url("Visit Our Website", 'https://t.me/PinterestDownloaderdlBot/PinterestDownloader')],
                [Button.url("Contact Us", 'https://t.me/m70_vortex')]
            ]
        )
    except Exception as e:
        logger.error(f"Error in /start command: {e}")
        await event.respond("An error occurred while processing your request.")

@bot.on(events.NewMessage(pattern='/broadcast'))
async def broadcast(event):
    if event.sender_id != ADMIN_ID:
        await event.respond("You are not authorized to use this command.")
        return

    try:
        if not hasattr(event.message, 'reply_to') or not event.message.reply_to:
            await event.respond("Please reply to a message to broadcast.")
            return

        await send_text(bot, event, [ADMIN_ID])
    except Exception as e:
        logger.error(f"Error in /broadcast command: {e}")
        await event.respond("An error occurred while broadcasting the message.")

@bot.on(events.NewMessage(pattern='/users'))
async def users(event):
    if event.sender_id != ADMIN_ID:
        await event.respond("You are not authorized to use this command.")
        return

    try:
        total_users = users_collection.count_documents({})
        await event.respond(f"Total number of users: {total_users}")
    except Exception as e:
        logger.error(f"Error in /users command: {e}")
        await event.respond("An error occurred while retrieving the user count.")

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update:
        asyncio.run(bot.process_new_message(update))
    return '', 200

# Start Flask server
if __name__ == '__main__':
    from threading import Thread
    
    def start_flask():
        app.run(host='0.0.0.0', port=PORT)
    
    # Start Flask in a separate thread
    flask_thread = Thread(target=start_flask)
    flask_thread.start()
    
    # Start the Telegram bot
    try:
        bot.run_until_disconnected()
    except Exception as e:
        logger.error(f"Error in bot execution: {e}")
