import datetime
import json
import logging
import os
import random

import pytz
import yaml
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes, MessageHandler, filters)


class Bot:

    def __init__(self, token: str) -> None:
        self.app = Application.builder().token(token).build()
        self.app.add_error_handler(self.error_handler)
        self.app.add_handler(CommandHandler("start", self.help))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("meow", self.meow))
        self.app.add_handler(CommandHandler("greet", self.greet))
        self.app.add_handler(CommandHandler("chance", self.chance))
        self.app.add_handler(CommandHandler("fortune", self.fortune))
        self.app.add_handler(CommandHandler("pick", self.pick))
        self.app.add_handler(CommandHandler("dice", self.dice))
        self.app.add_handler(CommandHandler("reminder", self.reminder))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.echo))
        if os.path.exists(config['bot']['reminder']['file']): self.load_timers()

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        E = context.error
        logger.warning(f'{type(E)}:{E.args}')

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(config['bot']['commands']['help']['message'], reply_to_message_id=update.message.id)

    async def meow(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = random.choices(list(config['bot']['commands']['meow']['choices'].keys()), weights=config['bot']['commands']['meow']['choices'].values(), k=1)[0]
        await update.message.reply_text(text)

    async def greet(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = f'Hi {update.effective_user.full_name}'
        await update.message.reply_text(text, reply_to_message_id=update.message.id)

    def roll_chance(self):
        return random.randint(config['bot']['commands']['chance']['min'], config['bot']['commands']['chance']['max'])

    async def chance(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args):
            text = '\n'.join([f"{i}: {self.roll_chance()}%" for i in context.args])
        else:
            text = f'機率: {self.roll_chance()}%'
        await update.message.reply_text(text, reply_to_message_id=update.message.id)

    def roll_fortune(self):
        return random.choices(list(config['bot']['commands']['fortune']['choices'].keys()), weights=config['bot']['commands']['fortune']['choices'].values(), k=1)[0]

    async def fortune(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args):
            text = '\n'.join([f"{i}: {self.roll_fortune()}" for i in context.args])
        else:
            text = f'運勢: {self.roll_fortune()}'
        await update.message.reply_text(text, reply_to_message_id=update.message.id)

    async def pick(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args):
            text = random.choice(context.args)
        else:
            text = 'Nothing to pick!'
        await update.message.reply_text(text, reply_to_message_id=update.message.id)

    async def dice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_dice()

    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(update.message.text, reply_to_message_id=update.message.id)

    async def reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args) > 0:
            action = context.args.pop(0)
            match action:
                case 'get':
                    await self.get_reminder(update, context)
                case 'add':
                    await self.add_reminder(update, context)
                case 'remove':
                    await self.remove_reminder(update, context)
                case 'clear':
                    await self.clear_reminder(update, context)
        else:
            await self.get_reminder(update, context)

    async def get_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_message.chat_id
        jobs = context.job_queue.jobs(f'{chat_id}@.+')
        if jobs:
            text = '\n'.join([f"{job.name.split('@')[-1]}, next at {job.next_t.strftime('%Y/%m/%d %H:%M:%S')}" for job in jobs])
        else:
            text = 'Reminder not found!'
        await update.message.reply_text(text, reply_to_message_id=update.message.id)

    async def add_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            chat_id = update.effective_message.chat_id
            hour, minute = context.args[0].split(':')
            tz = pytz.timezone(config['bot']['reminder']['timezone'])
            timer = datetime.time(int(hour), int(minute), tzinfo=tz)
        except:
            await update.message.reply_text('Invalid time!', reply_to_message_id=update.message.id)
        try:
            context.job_queue.run_daily(self.send_reminder, timer, name=f'{chat_id}@{timer.strftime("%H:%M")}', chat_id=chat_id)
            await update.message.reply_text(f'Send reminder at {timer.strftime("%H:%M")}', reply_to_message_id=update.message.id)
        finally:
            self.save_timers()

    async def remove_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.message.chat_id
        jobs = context.job_queue.get_jobs_by_name(f'{chat_id}@{context.args[0]}')
        if jobs:
            try:
                jobs[0].schedule_removal()
                await update.message.reply_text(f'Remove reminder at {context.args[0]}', reply_to_message_id=update.message.id)
            finally:
                self.save_timers()
        else:
            await update.message.reply_text(f'Reminder not found!', reply_to_message_id=update.message.id)

    async def clear_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.message.chat_id
        jobs = context.job_queue.jobs(f'{chat_id}@.+')
        for job in jobs:
            try:
                job.schedule_removal()
                await update.message.reply_text(f'Remove reminder at {job.name.split("@")[-1]}', reply_to_message_id=update.message.id)
            finally:
                self.save_timers()

    async def send_reminder(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        await context.bot.send_message(context.job.chat_id, text=config['bot']['reminder']['message'])

    def save_timers(self):
        jobs = [job.name for job in self.app.job_queue.jobs()]
        with open(config['bot']['reminder']['file'], 'w', encoding='utf-8') as f:
            json.dump(jobs, f)

    def load_timers(self):
        with open(config['bot']['reminder']['file'], 'r', encoding='utf-8') as f:
            jobs = json.load(f)
        for job in jobs:
            chat_id, hour_minute = job.split('@')
            hour, minute = hour_minute.split(':')
            tz = pytz.timezone(config['bot']['reminder']['timezone'])
            timer = datetime.time(int(hour), int(minute), tzinfo=tz)
            self.app.job_queue.run_daily(self.send_reminder, timer, name=job, chat_id=chat_id)


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', type=str, default="config.yaml")
    parser.add_argument('--log-level', type=int, default=30)
    args = parser.parse_args()
    with open(args.f, encoding='utf-8') as f:
        config = yaml.load(f, yaml.SafeLoader)
    logging.basicConfig(
        format=config['logging']['format'] or '%(asctime)s %(levelname)s %(name)s: %(message)s',
        level=config['logging']['level'] or args.log_level,
    )
    logger = logging.getLogger('App')
    logger.debug(f'GIL enabled: {sys._is_gil_enabled()}')
    logger.info(f'Config file: {args.f}')
    bot = Bot(config['bot']['token'])
    bot.app.run_polling(allowed_updates=Update.ALL_TYPES)
