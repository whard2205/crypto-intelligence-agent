from __future__ import annotations
import logging
import re
import uuid
from datetime import datetime, timezone

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config.settings import Settings, get_settings
from data_sources.factory import build_adapters
from graph.pipeline import build_graph
from graph.trend import inject_trend_signal
from publishers.telegram_publisher import format_history_summary, format_intelligence_report
from storage.report_history import ReportHistoryRepository

logger = logging.getLogger(__name__)

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9]{2,19}$")

_DEFAULT_HISTORY_LIMIT = 5
_MAX_HISTORY_LIMIT     = 10

HELP_TEXT = (
    "📊 <b>Crypto Intelligence Bot</b>\n\n"
    "<b>Commands:</b>\n"
    "/help — Show this message\n"
    "/report — Generate reports for all watched symbols\n"
    "/report &lt;SYMBOL&gt; — Generate report for one symbol\n"
    "/history — Show last 5 reports for all watched symbols\n"
    "/history &lt;SYMBOL&gt; — Show last 5 reports for one symbol\n"
    "/history &lt;SYMBOL&gt; &lt;N&gt; — Show last N reports (max 10)\n\n"
    "<b>Examples:</b>\n"
    "<code>/report BTCUSDT</code>\n"
    "<code>/report ETHUSDT</code>\n"
    "<code>/report SOLUSDT</code>\n\n"
    "<i>Powered by ICT/SMC rule-based analysis. No paid APIs required.</i>"
)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await help_command(update, context)


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    graph              = context.bot_data["graph"]
    repo: ReportHistoryRepository | None = context.bot_data.get("repo")

    args = list(context.args or [])

    if args:
        symbol = args[0].upper()
        if not _SYMBOL_RE.match(symbol):
            await update.message.reply_text(
                f"❌ Invalid symbol: <code>{symbol}</code>\n"
                "Use uppercase letters only, e.g. <code>/report BTCUSDT</code>",
                parse_mode="HTML",
            )
            return
        symbols = [symbol]
    else:
        symbols = [s.strip() for s in settings.WATCH_SYMBOLS.split(",") if s.strip()]
        await update.message.reply_text(
            f"⏳ Generating reports for {', '.join(symbols)}…",
            parse_mode="HTML",
        )

    for symbol in symbols:
        try:
            result = await graph.ainvoke(_make_initial_state(symbol))
            report = result["report"]

            if repo:
                report = await inject_trend_signal(report, repo)
                if not report.get("error"):
                    try:
                        await repo.save(report)
                    except Exception:
                        logger.exception("Failed to save report for %s to history", symbol)

            msg = format_intelligence_report(report, settings.DISPLAY_TIMEZONE)
            await update.message.reply_text(msg, parse_mode="HTML")
        except Exception as exc:
            logger.exception("Pipeline error for %s", symbol)
            await update.message.reply_text(
                f"❌ Failed to generate report for <code>{symbol}</code>: {exc}",
                parse_mode="HTML",
            )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings                   = context.bot_data["settings"]
    repo: ReportHistoryRepository | None = context.bot_data.get("repo")

    if not repo:
        await update.message.reply_text(
            "⚠️ History is not available (storage not initialised).",
            parse_mode="HTML",
        )
        return

    args = list(context.args or [])

    limit = _DEFAULT_HISTORY_LIMIT

    if args:
        symbol = args[0].upper()
        if not _SYMBOL_RE.match(symbol):
            await update.message.reply_text(
                f"❌ Invalid symbol: <code>{symbol}</code>\n"
                "Use uppercase letters only, e.g. <code>/history BTCUSDT</code>",
                parse_mode="HTML",
            )
            return
        symbols = [symbol]

        if len(args) >= 2:
            try:
                limit = int(args[1])
            except (ValueError, TypeError):
                pass  # keep default
        limit = min(max(limit, 1), _MAX_HISTORY_LIMIT)
    else:
        symbols = [s.strip() for s in settings.WATCH_SYMBOLS.split(",") if s.strip()]

    for symbol in symbols:
        try:
            records = await repo.get_latest(symbol, limit=limit)
            msg = format_history_summary(symbol, records, settings.DISPLAY_TIMEZONE)
            await update.message.reply_text(msg, parse_mode="HTML")
        except Exception as exc:
            logger.exception("Failed to fetch history for %s", symbol)
            await update.message.reply_text(
                f"❌ Failed to fetch history for <code>{symbol}</code>: {exc}",
                parse_mode="HTML",
            )


# ---------------------------------------------------------------------------
# Async post-init hook: runs in the bot's event loop before polling starts
# ---------------------------------------------------------------------------

_BOT_COMMANDS = [
    BotCommand("start",   "Show help"),
    BotCommand("help",    "Show help message"),
    BotCommand("report",  "Generate report for all watched symbols"),
    BotCommand("history", "Show last 5 reports per symbol"),
]


async def _post_init(application: Application) -> None:
    await setup_bot_data(application, application.bot_data["settings"])
    await application.bot.set_my_commands(_BOT_COMMANDS)
    logger.info("Telegram bot commands registered: %s", [c.command for c in _BOT_COMMANDS])


# ---------------------------------------------------------------------------
# Bot data initializer for FastAPI-integrated lifecycle
# ---------------------------------------------------------------------------

async def setup_bot_data(application: Application, settings: Settings) -> None:
    repo = ReportHistoryRepository(settings.DB_PATH)
    await repo.init_db()
    application.bot_data["repo"] = repo
    logger.info("Report history DB ready at %s", settings.DB_PATH)


# ---------------------------------------------------------------------------
# Bot builder
# ---------------------------------------------------------------------------

def build_bot(settings: Settings) -> Application:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN is not configured. "
            "Add it to your .env file and restart."
        )

    adapters = build_adapters(settings)
    graph    = build_graph(settings, **adapters)

    app = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.bot_data["settings"] = settings
    app.bot_data["graph"]    = graph

    app.add_handler(CommandHandler("start",  start_command))
    app.add_handler(CommandHandler("help",   help_command))
    app.add_handler(CommandHandler("report",  report_command))
    app.add_handler(CommandHandler("history", history_command))

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _make_initial_state(symbol: str) -> dict:
    return {
        "run_id":                    str(uuid.uuid4()),
        "symbol":                    symbol,
        "requested_at":              datetime.now(timezone.utc).isoformat(),
        "price_data":                None,
        "news_data":                 [],
        "onchain_data":              None,
        "social_data":               None,
        "funding_rate_data":         None,
        "context":                   None,
        "sentiment_analysis":        None,
        "market_structure_analysis": None,
        "risk_analysis":             None,
        "analysis":                  None,
        "report":                    None,
        "data_gaps":                 [],
        "errors":                    [],
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    s = get_settings()
    build_bot(s).run_polling(allowed_updates=Update.ALL_TYPES)
