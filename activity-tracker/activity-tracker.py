import asyncio
import csv
import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple, Dict, Set

import discord
from discord.ext import commands

from core import checks
from core.models import PermissionLevel, getLogger
from core.utils import safe_typing

logger = getLogger(__name__)


# ---- helpers ----
MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _utcnow() -> datetime:
    return discord.utils.utcnow()


def month_bounds(month: Optional[int] = None, year: Optional[int] = None,
                 *, keyword: Optional[str] = None) -> Tuple[datetime, datetime, str]:
    """
    Returns start (inclusive) and end (exclusive) UTC datetimes for a calendar month.
    If keyword is provided, accepts "this" or "last" for this month or previous month.
    """
    now = _utcnow()
    if keyword:
        kw = keyword.lower()
        if kw in {"this", "this-month", "current"}:
            year, month = now.year, now.month
        elif kw in {"last", "last-month", "previous"}:
            prev = (now.replace(day=1) - timedelta(days=1))
            year, month = prev.year, prev.month
        else:
            raise ValueError("Unknown keyword. Use 'this' or 'last'.")
    elif month is None or year is None:
        # default: last month
        prev = (now.replace(day=1) - timedelta(days=1))
        year, month = prev.year, prev.month

    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    label = f"{year:04d}-{month:02d}"
    return start, end, label


def parse_period_arg(arg: Optional[str]) -> Tuple[datetime, datetime, str]:
    if not arg:
        return month_bounds()
    s = arg.strip().lower()
    if s in {"this", "last", "this-month", "last-month", "previous", "current"}:
        return month_bounds(keyword=s)
    # Accept YYYY-MM
    try:
        if "-" in s:
            parts = s.split("-")
            if len(parts) == 2:
                y, m = int(parts[0]), int(parts[1])
                return month_bounds(month=m, year=y)
    except Exception:
        pass
    # Accept MonthName YYYY
    for name, m in MONTH_NAMES.items():
        if s.startswith(name):
            rest = s[len(name):].strip().strip(", ")
            try:
                y = int(rest)
                return month_bounds(month=m, year=y)
            except Exception:
                break
    raise commands.BadArgument("Invalid period. Use YYYY-MM, 'this', 'last', or 'Month YYYY'.")


@dataclass
class CaseStats:
    key: str
    channel_id: str
    created_at: Optional[datetime]
    closed_at: Optional[datetime]
    recipient_id: str
    recipient_name: str
    creator_id: Optional[str]
    closer_id: Optional[str]
    total_messages: int
    mod_messages: int
    user_messages: int
    first_response_seconds: Optional[int]


def iso_to_dt(iso_str: Optional[str]) -> Optional[datetime]:
    if not iso_str:
        return None
    try:
        # fromisoformat handles both with and without timezone
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        try:
            # Fallback parse for formats that may include 'Z'
            return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return None


def compute_case_stats(doc: dict, *, allowed_types: Optional[Set[str]] = None) -> CaseStats:
    created_at = iso_to_dt(doc.get("created_at"))
    closed_at = iso_to_dt(doc.get("closed_at"))
    recipient = doc.get("recipient") or {}
    creator = doc.get("creator") or {}
    closer = doc.get("closer") or {}

    messages: List[dict] = doc.get("messages") or []

    mod_msgs = [
        m
        for m in messages
        if (m.get("author") or {}).get("mod") and (allowed_types is None or m.get("type") in allowed_types)
    ]
    user_msgs = [m for m in messages if not (m.get("author") or {}).get("mod")]

    # first response time: first mod message after first user message
    first_user = iso_to_dt(user_msgs[0]["timestamp"]) if user_msgs else None
    first_mod = iso_to_dt(mod_msgs[0]["timestamp"]) if mod_msgs else None
    first_resp = None
    if first_user and first_mod:
        delta = (first_mod - first_user).total_seconds()
        if delta >= 0:
            first_resp = int(delta)

    return CaseStats(
        key=str(doc.get("key")),
        channel_id=str(doc.get("channel_id")),
        created_at=created_at,
        closed_at=closed_at,
        recipient_id=str(recipient.get("id")) if recipient else "",
        recipient_name=f"{recipient.get('name','')}#{recipient.get('discriminator','')}" if recipient else "",
        creator_id=str(creator.get("id")) if creator else None,
        closer_id=str((closer or {}).get("id")) if closer else None,
        total_messages=len(messages),
        mod_messages=len(mod_msgs),
        user_messages=len(user_msgs),
        first_response_seconds=first_resp,
    )


def stats_to_csv(stats: Iterable[CaseStats]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "key",
        "channel_id",
        "created_at",
        "closed_at",
        "duration_seconds",
        "recipient_id",
        "recipient_tag",
        "creator_id",
        "closer_id",
        "total_messages",
        "mod_messages",
        "user_messages",
        "first_response_seconds",
    ])
    for s in stats:
        duration = None
        if s.created_at and s.closed_at:
            duration = int((s.closed_at - s.created_at).total_seconds())
        writer.writerow([
            s.key,
            s.channel_id,
            s.created_at.isoformat() if s.created_at else "",
            s.closed_at.isoformat() if s.closed_at else "",
            duration if duration is not None else "",
            s.recipient_id,
            s.recipient_name,
            s.creator_id or "",
            s.closer_id or "",
            s.total_messages,
            s.mod_messages,
            s.user_messages,
            s.first_response_seconds if s.first_response_seconds is not None else "",
        ])
    return out.getvalue().encode("utf-8")


def aggregate_leaderboard(
    docs: List[dict], *, allowed_types: Optional[Set[str]] = None
) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    """Returns (closers, senders) ranked lists.
    closers: list of (user_id, closed_count)
    senders: list of (user_id, mod_message_count)
    """
    close_counts: Dict[int, int] = {}
    send_counts: Dict[int, int] = {}

    for doc in docs:
        closer = (doc.get("closer") or {}).get("id")
        if closer:
            try:
                uid = int(closer)
                close_counts[uid] = close_counts.get(uid, 0) + 1
            except ValueError:
                pass
        for m in doc.get("messages") or []:
            if allowed_types is not None and m.get("type") not in allowed_types:
                continue
            a = m.get("author") or {}
            if a.get("mod"):
                try:
                    uid = int(a.get("id"))
                    send_counts[uid] = send_counts.get(uid, 0) + 1
                except (TypeError, ValueError):
                    pass

    closers = sorted(close_counts.items(), key=lambda kv: kv[1], reverse=True)
    senders = sorted(send_counts.items(), key=lambda kv: kv[1], reverse=True)
    return closers, senders


class CaseExporter(commands.Cog):
    """Export closed/opened cases by month and show leaderboards."""

    def __init__(self, bot):
        self.bot = bot
        # Very small in-memory cache to minimize DB calls across quick successive commands
        # Key: (field, start_iso, end_iso) -> (cached_at, docs)
        self._cache: Dict[Tuple[str, str, str], Tuple[datetime, List[dict]]] = {}
        self._cache_ttl = timedelta(minutes=5)
        # defaults for plugin config
        self._default_cfg = {"count_replies_only": False}

    # ---- config helpers ----
    async def _get_cfg(self) -> Dict[str, bool]:
        try:
            coll = self.bot.api.get_plugin_partition(self)
            doc = await coll.find_one({"_id": str(self.bot.guild_id)})
            if not doc:
                return dict(self._default_cfg)
            cfg = dict(self._default_cfg)
            cfg.update({k: v for k, v in doc.items() if k in cfg})
            return cfg
        except Exception:
            logger.debug("Failed reading plugin config; using defaults.", exc_info=True)
            return dict(self._default_cfg)

    async def _save_cfg(self, cfg: Dict[str, bool]) -> None:
        try:
            coll = self.bot.api.get_plugin_partition(self)
            payload = dict(self._default_cfg)
            payload.update(cfg)
            payload["_id"] = str(self.bot.guild_id)
            await coll.update_one({"_id": payload["_id"]}, {"$set": payload}, upsert=True)
        except Exception:
            logger.debug("Failed saving plugin config.", exc_info=True)

    @staticmethod
    def _allowed_types(cfg: Dict[str, bool]) -> Optional[Set[str]]:
        return {"thread_message", "anonymous"} if cfg.get("count_replies_only") else None

    # ---- core queries ----
    async def _query_logs_in_range(self, start: datetime, end: datetime, *, field: str) -> List[dict]:
        """
        Query logs by ISO 8601 string range on a given field (created_at/closed_at).
        Falls back to client-side filtering if necessary.
        """
        start_iso = start.isoformat()
        end_iso = end.isoformat()
        guild_id = str(self.bot.guild_id)

        coll = self.bot.api.db.logs
        query = {"guild_id": guild_id, field: {"$gte": start_iso, "$lt": end_iso}}

        # Cache check
        cache_key = (field, start_iso, end_iso)
        cached = self._cache.get(cache_key)
        if cached and (_utcnow() - cached[0]) <= self._cache_ttl:
            return cached[1]

        # Projection to reduce payload; we still need messages for metrics
        projection = {
            "key": 1,
            "channel_id": 1,
            "created_at": 1,
            "closed_at": 1,
            "recipient": 1,
            "creator": 1,
            "closer": 1,
            # only keep mod flag, author id and timestamp in messages
            "messages.author.mod": 1,
            "messages.author.id": 1,
            "messages.timestamp": 1,
            "messages.type": 1,
        }
        try:
            docs = await coll.find(query, projection).to_list(None)
            # Some entries may store None for closed_at; keep filter strict in Python too
            def in_range(d: dict) -> bool:
                v = d.get(field)
                if not v:
                    return False
                dt = iso_to_dt(v)
                return bool(dt and start <= dt < end)

            result = [d for d in docs if in_range(d)]
            self._cache[cache_key] = (_utcnow(), result)
            return result
        except Exception:
            logger.debug("DB-range query failed; falling back to client filtering.", exc_info=True)
            docs = await coll.find({"guild_id": guild_id}, projection).to_list(None)
            res = []
            for d in docs:
                v = d.get(field)
                dt = iso_to_dt(v)
                if dt and start <= dt < end:
                    res.append(d)
            self._cache[cache_key] = (_utcnow(), res)
            return res

    # ---- summaries & metrics ----
    @staticmethod
    def _format_duration(seconds: Optional[int]) -> str:
        if seconds is None:
            return "—"
        mins, sec = divmod(int(seconds), 60)
        hrs, mins = divmod(mins, 60)
        days, hrs = divmod(hrs, 24)
        if days:
            return f"{days}d {hrs}h {mins}m"
        if hrs:
            return f"{hrs}h {mins}m"
        if mins:
            return f"{mins}m {sec}s"
        return f"{sec}s"

    @staticmethod
    def _calc_summary(stats: List[CaseStats]) -> Dict[str, Optional[float]]:
        import math
        durations = [
            (s.closed_at - s.created_at).total_seconds()
            for s in stats
            if s.created_at and s.closed_at
        ]
        frts = [s.first_response_seconds for s in stats if s.first_response_seconds is not None]

        def _avg(arr: List[float]) -> Optional[float]:
            return sum(arr) / len(arr) if arr else None

        def _median(arr: List[float]) -> Optional[float]:
            if not arr:
                return None
            arr = sorted(arr)
            mid = len(arr) // 2
            if len(arr) % 2 == 1:
                return float(arr[mid])
            return (arr[mid - 1] + arr[mid]) / 2.0

        # SLA buckets for FRT
        buckets = {"<=5m": 0, "<=30m": 0, "<=2h": 0, ">2h": 0}
        for v in frts:
            if v <= 5 * 60:
                buckets["<=5m"] += 1
            elif v <= 30 * 60:
                buckets["<=30m"] += 1
            elif v <= 2 * 3600:
                buckets["<=2h"] += 1
            else:
                buckets[">2h"] += 1

        total = len(frts) or 1
        sla_pct = {k: (v * 100.0) / total for k, v in buckets.items()}

        return {
            "count": len(stats),
            "avg_duration": _avg(durations),
            "median_duration": _median(durations),
            "avg_frt": _avg(frts),
            "median_frt": _median(frts),
            "sla_5m": sla_pct["<=5m"],
            "sla_30m": sla_pct["<=30m"],
            "sla_2h": sla_pct["<=2h"],
            "sla_gt2h": sla_pct[">2h"],
        }

    # ---- commands ----
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @commands.group(name="cases", invoke_without_command=True)
    async def cases(self, ctx: commands.Context):
        """
        Export monthly case data and view leaderboards.
        """
        ex = (
            "Quick actions:\n"
            f"• `{self.bot.prefix}cases export` → last month CSV (closed)\n"
            f"• `{self.bot.prefix}cases export this json` → this month JSON\n"
            f"• `{self.bot.prefix}cases export 2025-11` → Nov 2025 CSV\n"
            f"• `{self.bot.prefix}cases lb` → leaderboard 30d\n"
            f"• `{self.bot.prefix}cases summary last` → last month summary\n"
            "\nSettings:\n"
            f"• `{self.bot.prefix}cases cfg` → view settings\n"
            f"• `{self.bot.prefix}cases cfg replies-only on` → count replies only\n"
        )
        embed = discord.Embed(title="Cases", description=ex, color=self.bot.main_color)
        await ctx.send(embed=embed)

    # ---- friendly parsing ----
    @staticmethod
    def _parse_export_args(argline: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse order-agnostic tokens for export.

        Returns (period, kind, fmt)
        """
        if not argline:
            return None, None, None
        tokens = [t.strip() for t in argline.split() if t.strip()]
        if not tokens:
            return None, None, None

        kind = None
        fmt = None
        period_str = None

        # normalize maps
        kind_map = {
            "closed": "closed",
            "close": "closed",
            "c": "closed",
            "opened": "opened",
            "open": "opened",
            "o": "opened",
        }
        fmt_map = {"csv": "csv", "json": "json", "js": "json"}
        month_token = None
        year_token = None

        for tok in tokens:
            low = tok.lower()
            if low in kind_map and not kind:
                kind = kind_map[low]
                continue
            if low in fmt_map and not fmt:
                fmt = fmt_map[low]
                continue
            if low in {"this", "last", "current", "previous", "prev"}:
                period_str = low if low != "prev" else "last"
                continue
            # YYYY-MM
            if "-" in low:
                parts = low.split("-")
                if len(parts) == 2 and all(p.isdigit() for p in parts):
                    period_str = low
                    continue
            # 4-digit year or month name captured separately
            if low.isdigit() and len(low) == 4:
                year_token = low
                continue
            if low in MONTH_NAMES:
                month_token = low
                continue

        if not period_str and (month_token and year_token):
            # Compose "Month YYYY"
            period_str = f"{month_token.capitalize()} {year_token}"

        return period_str, kind, fmt

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @cases.command(name="export", aliases=["x", "exp", "cexport"]) 
    async def cases_export(self, ctx: commands.Context, *, args: Optional[str] = None):
        """Export case data for a month to CSV/JSON.

        Arguments can be in any order. Examples:
        - 2025-11 json
        - this opened csv
        - november 2025
        Defaults: last month, closed, csv
        """
        period, kind, fmt = self._parse_export_args(args)
        try:
            start, end, label = parse_period_arg(period)
        except commands.BadArgument:
            start, end, label = month_bounds()  # default last month

        kind = (kind or "closed").lower()
        fmt = (fmt or "csv").lower()
        if kind not in {"closed", "opened"}:
            return await ctx.send("Invalid kind. Use 'opened' or 'closed'.")
        if fmt not in {"csv", "json"}:
            return await ctx.send("Invalid format. Use 'csv' or 'json'.")

        field = "closed_at" if kind == "closed" else "created_at"
        async with safe_typing(ctx):
            pass
        docs = await self._query_logs_in_range(start, end, field=field)
        if not docs:
            return await ctx.send(f"No {kind} cases found for {label}.")

        # Build stats (respect config)
        cfg = await self._get_cfg()
        allowed = self._allowed_types(cfg)
        stats: List[CaseStats] = [compute_case_stats(d, allowed_types=allowed) for d in docs]

        # Friendly summary embed alongside file
        summary = self._calc_summary(stats)
        embed = discord.Embed(
            title=f"Cases {kind.capitalize()} — {label}", color=self.bot.main_color
        )
        embed.add_field(name="Cases", value=str(summary["count"]))
        embed.add_field(
            name="Avg Duration",
            value=self._format_duration(int(summary["avg_duration"])) if summary["avg_duration"] else "—",
        )
        embed.add_field(
            name="Median Duration",
            value=self._format_duration(int(summary["median_duration"])) if summary["median_duration"] else "—",
        )
        embed.add_field(
            name="Avg First Response",
            value=self._format_duration(int(summary["avg_frt"])) if summary["avg_frt"] else "—",
        )
        embed.add_field(
            name="Median First Response",
            value=self._format_duration(int(summary["median_frt"])) if summary["median_frt"] else "—",
        )
        embed.add_field(
            name="SLA (<=5m / 30m / 2h / >2h)",
            value=(
                f"{summary['sla_5m']:.0f}% / {summary['sla_30m']:.0f}% / "
                f"{summary['sla_2h']:.0f}% / {summary['sla_gt2h']:.0f}%"
            ),
            inline=False,
        )

        if fmt == "csv":
            payload = stats_to_csv(stats)
            filename = f"cases_{kind}_{label}.csv"
            if allowed is not None:
                embed.set_footer(text="Messages counted: Replies only (thread_message, anonymous)")
            return await ctx.send(embed=embed, file=discord.File(io.BytesIO(payload), filename=filename))
        else:
            # JSON export: include raw keys & some computed fields
            serialised = []
            for s in stats:
                duration = None
                if s.created_at and s.closed_at:
                    duration = int((s.closed_at - s.created_at).total_seconds())
                serialised.append({
                    "key": s.key,
                    "channel_id": s.channel_id,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "closed_at": s.closed_at.isoformat() if s.closed_at else None,
                    "duration_seconds": duration,
                    "recipient_id": s.recipient_id,
                    "recipient_tag": s.recipient_name,
                    "creator_id": s.creator_id,
                    "closer_id": s.closer_id,
                    "total_messages": s.total_messages,
                    "mod_messages": s.mod_messages,
                    "user_messages": s.user_messages,
                    "first_response_seconds": s.first_response_seconds,
                })
            import json
            b = json.dumps(serialised, indent=2).encode("utf-8")
            filename = f"cases_{kind}_{label}.json"
            if allowed is not None:
                embed.set_footer(text="Messages counted: Replies only (thread_message, anonymous)")
            return await ctx.send(embed=embed, file=discord.File(io.BytesIO(b), filename=filename))

    @checks.has_permissions(PermissionLevel.MODERATOR)
    @cases.command(name="leaderboard", aliases=["lb", "leaders", "board", "clb"]) 
    async def cases_leaderboard(self, ctx: commands.Context, *, period: Optional[str] = None):
        """Show staff activity leaderboard for a month or last 30 days.

        period: YYYY-MM | this | last | Month YYYY | 30d
        Default is last 30 days if omitted.
        """
        # Decide range
        if period and period.strip().lower().endswith("d"):
            try:
                days = int(period.strip().lower()[:-1] or "30")
            except ValueError:
                return await ctx.send("Invalid days value. Try '30d'.")
            end = _utcnow().replace(tzinfo=timezone.utc)
            start = end - timedelta(days=days)
            label = f"last {days} days"
        else:
            # treat as calendar period
            try:
                start, end, label = parse_period_arg(period) if period else (None, None, None)
                if start is None:
                    end = _utcnow().replace(tzinfo=timezone.utc)
                    start = end - timedelta(days=30)
                    label = "last 30 days"
            except commands.BadArgument:
                end = _utcnow().replace(tzinfo=timezone.utc)
                start = end - timedelta(days=30)
                label = "last 30 days"

        async with safe_typing(ctx):
            pass
        docs = await self._query_logs_in_range(start, end, field="closed_at")
        if not docs:
            return await ctx.send(f"No closed cases found for {label}.")

        cfg = await self._get_cfg()
        allowed = self._allowed_types(cfg)
        closers, senders = aggregate_leaderboard(docs, allowed_types=allowed)

        # Build a safe name map from logs (no pings); fall back to cached member names
        name_map: Dict[int, str] = {}
        for doc in docs:
            closer = (doc.get("closer") or {})
            if closer and closer.get("id") and closer.get("name"):
                try:
                    uid = int(closer["id"])
                    name = closer.get("name", "")
                    disc = closer.get("discriminator", "")
                    tag = f"{name}#{disc}" if disc and disc != "0" else name
                    if uid not in name_map and tag:
                        name_map[uid] = tag
                except (TypeError, ValueError):
                    pass
            for m in doc.get("messages") or []:
                if allowed is not None and m.get("type") not in allowed:
                    continue
                a = m.get("author") or {}
                if a.get("mod"):
                    try:
                        uid = int(a.get("id"))
                        nm = a.get("name", "")
                        disc = a.get("discriminator", "")
                        tag = f"{nm}#{disc}" if disc and disc != "0" else nm
                        if uid not in name_map and tag:
                            name_map[uid] = tag
                    except (TypeError, ValueError):
                        pass

        # Fill remaining from guild cache without mentions
        guild = self.bot.modmail_guild
        if guild:
            for uid, _ in list(closers) + list(senders):
                if uid in name_map:
                    continue
                m = guild.get_member(uid)
                if m:
                    name_map[uid] = m.display_name

        # First responder leaderboard (mod who posted first mod message)
        first_responder_counts: Dict[int, int] = {}
        for doc in docs:
            msgs = doc.get("messages") or []
            # find first user and first mod
            first_mod = None
            first_user = None
            for m in msgs:
                ts = iso_to_dt(m.get("timestamp"))
                a = m.get("author") or {}
                if not first_user and not a.get("mod"):
                    first_user = ts
                if not first_mod and a.get("mod"):
                    first_mod = (ts, a.get("id"))
                if first_user and first_mod:
                    break
            if first_user and first_mod and first_mod[0] and first_mod[1]:
                try:
                    uid = int(first_mod[1])
                    first_responder_counts[uid] = first_responder_counts.get(uid, 0) + 1
                except (TypeError, ValueError):
                    pass
        first_responders = sorted(first_responder_counts.items(), key=lambda kv: kv[1], reverse=True)

        # Render embed top 10
        embed = discord.Embed(title=f"Support Activity — {label}", color=self.bot.main_color)

        def fmt_users(items: List[Tuple[int, int]], title: str) -> str:
            if not items:
                return "No data"
            lines = []
            for rank, (uid, count) in enumerate(items[:10], start=1):
                base = name_map.get(uid)
                if not base:
                    member = self.bot.modmail_guild and self.bot.modmail_guild.get_member(uid)
                    base = member.display_name if member else f"User {uid}"
                lines.append(f"{rank}. {base} ({uid}) — {count}")
            return "\n".join(lines)

        embed.add_field(name="Threads Closed", value=fmt_users(closers, "Closed"), inline=False)
        embed.add_field(name="Messages Sent", value=fmt_users(senders, "Messages"), inline=False)
        embed.add_field(
            name="First Responders",
            value=("No data" if not first_responders else fmt_users(first_responders, "First Responded")),
            inline=False,
        )
        if allowed is not None:
            embed.set_footer(text="Messages counted: Replies only (thread_message, anonymous)")
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.MODERATOR)
    @cases.command(name="summary", aliases=["sum", "overview", "csummary"]) 
    async def cases_summary(self, ctx: commands.Context, *, period: Optional[str] = None):
        """Compact stats overview for a period (default: last month)."""
        try:
            start, end, label = parse_period_arg(period)
        except commands.BadArgument:
            start, end, label = month_bounds()  # default last month

        async with safe_typing(ctx):
            pass
        # One query for closed, one for opened (kept cached if re-used elsewhere)
        closed_docs = await self._query_logs_in_range(start, end, field="closed_at")
        opened_docs = await self._query_logs_in_range(start, end, field="created_at")

        cfg = await self._get_cfg()
        allowed = self._allowed_types(cfg)
        closed_stats = [compute_case_stats(d, allowed_types=allowed) for d in closed_docs]
        opened_stats = [compute_case_stats(d, allowed_types=allowed) for d in opened_docs]
        s_closed = self._calc_summary(closed_stats)
        s_opened = self._calc_summary(opened_stats)

        embed = discord.Embed(title=f"Cases Summary — {label}", color=self.bot.main_color)
        embed.add_field(
            name="Closed",
            value=(
                f"Count: {s_closed['count']}\n"
                f"Avg Dur: {self._format_duration(int(s_closed['avg_duration'])) if s_closed['avg_duration'] else '—'}\n"
                f"Median Dur: {self._format_duration(int(s_closed['median_duration'])) if s_closed['median_duration'] else '—'}\n"
                f"Avg FRT: {self._format_duration(int(s_closed['avg_frt'])) if s_closed['avg_frt'] else '—'}\n"
                f"SLA <=5m: {s_closed['sla_5m']:.0f}%"
            ),
            inline=True,
        )
        embed.add_field(
            name="Opened",
            value=(
                f"Count: {s_opened['count']}\n"
                f"Avg Dur: {self._format_duration(int(s_opened['avg_duration'])) if s_opened['avg_duration'] else '—'}\n"
                f"Median Dur: {self._format_duration(int(s_opened['median_duration'])) if s_opened['median_duration'] else '—'}\n"
                f"Avg FRT: {self._format_duration(int(s_opened['avg_frt'])) if s_opened['avg_frt'] else '—'}\n"
                f"SLA <=5m: {s_opened['sla_5m']:.0f}%"
            ),
            inline=True,
        )
        footer = "All times in UTC; exported data contains precise timestamps."
        if allowed is not None:
            footer += " Messages counted: Replies only."
        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.MODERATOR)
    @cases.command(name="monthly")
    async def cases_monthly(self, ctx: commands.Context):
        """One-shot: last month export (CSV, closed) + leaderboard."""
        # Export last month CSV
        await self.cases_export(ctx, args=None)
        # Leaderboard last month
        prev = ( _utcnow().replace(day=1) - timedelta(days=1) )
        label = f"{prev.year:04d}-{prev.month:02d}"
        await self.cases_leaderboard(ctx, period=label)

    # ---- configuration commands ----
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @cases.group(name="config", aliases=["cfg"], invoke_without_command=True)
    async def cases_config(self, ctx: commands.Context):
        """Show current configuration for Cases plugin."""
        cfg = await self._get_cfg()
        desc = (
            f"count_replies_only: {'on' if cfg.get('count_replies_only') else 'off'}\n\n"
            f"Toggle: `{self.bot.prefix}cases cfg replies-only on|off`"
        )
        embed = discord.Embed(title="Cases Config", description=desc, color=self.bot.main_color)
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @cases_config.command(name="replies-only", aliases=["reply-only", "replies", "reply"])
    async def cases_config_replies_only(self, ctx: commands.Context, state: str):
        """Count only staff replies (thread_message, anonymous) for metrics and leaderboards."""
        s = (state or "").strip().lower()
        truthy = {"on", "true", "yes", "y", "1", "enable", "enabled"}
        falsy = {"off", "false", "no", "n", "0", "disable", "disabled"}
        if s not in truthy | falsy:
            return await ctx.send("Invalid value. Use on/off.")
        cfg = await self._get_cfg()
        cfg["count_replies_only"] = s in truthy
        await self._save_cfg(cfg)
        await ctx.send(
            f"Messages counted set to: {'replies only' if cfg['count_replies_only'] else 'all staff messages'}."
        )


async def setup(bot):
    await bot.add_cog(CaseExporter(bot))
