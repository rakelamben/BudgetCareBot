import asyncio

from aiogram.types import BotCommand

from budgetcare.bot.dispatcher import create_bot


async def main() -> None:
    bot = create_bot()
    try:
        commands = [
            BotCommand(command="start", description="Mulai bot & pengaturan zona waktu"),
            BotCommand(
                command="goals", description="Lihat status target tabungan & hewan peliharaan"
            ),
            BotCommand(command="newgoal", description="Buat target tabungan baru"),
            BotCommand(command="feed", description="Catat setoran tabungan atau makan gratis ($0)"),
            BotCommand(command="undo", description="Batalkan setoran terakhir (<24 jam)"),
            BotCommand(command="settings", description="Pengaturan notifikasi, zona waktu & akun"),
            BotCommand(command="delete", description="Hapus target tabungan"),
            BotCommand(command="cancel", description="Batalkan aksi saat ini"),
            BotCommand(command="help", description="Petunjuk bantuan & informasi"),
        ]
        await bot.set_my_commands(commands)
        print("[SUCCESS] Telegram bot commands registered successfully!")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
