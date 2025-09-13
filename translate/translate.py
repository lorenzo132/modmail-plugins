"""
MIT License
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import discord, traceback, asyncio

from discord.ext import commands
from discord import User
from core import checks
from core.models import PermissionLevel

from mtranslate import translate
from googletrans import Translator
# Try multiple known paths for Modmail's paginator utility
PaginatorEmbedInterface = None  # type: ignore
try:
    from core.utils.paginator import PaginatorEmbedInterface  # type: ignore
except Exception:
    try:
        from cogs.utils.paginator import PaginatorEmbedInterface  # type: ignore
    except Exception:
        try:
            from utils.paginator import PaginatorEmbedInterface  # type: ignore
        except Exception:
            PaginatorEmbedInterface = None  # type: ignore


conv = {
    "ab": "Abkhaz",
    "aa": "Afar",
    "af": "Afrikaans",
    "ak": "Akan",
    "sq": "Albanian",
    "am": "Amharic",
    "ar": "Arabic",
    "an": "Aragonese",
    "hy": "Armenian",
    "as": "Assamese",
    "av": "Avaric",
    "ae": "Avestan",
    "ay": "Aymara",
    "az": "Azerbaijani",
    "bm": "Bambara",
    "ba": "Bashkir",
    "eu": "Basque",
    "be": "Belarusian",
    "bn": "Bengali",
    "bh": "Bihari",
    "bi": "Bislama",
    "bs": "Bosnian",
    "br": "Breton",
    "bg": "Bulgarian",
    "my": "Burmese",
    "ca": "Catalan",
    "ch": "Chamorro",
    "ce": "Chechen",
    "ny": "Nyanja",
    "zh": "Chinese",
    "cv": "Chuvash",
    "kw": "Cornish",
    "co": "Corsican",
    "cr": "Cree",
    "hr": "Croatian",
    "cs": "Czech",
    "da": "Danish",
    "dv": "Divehi",
    "nl": "Dutch",
    "dz": "Dzongkha",
    "en": "English",
    "eo": "Esperanto",
    "et": "Estonian",
    "ee": "Ewe",
    "fo": "Faroese",
    "fj": "Fijian",
    "fi": "Finnish",
    "fr": "French",
    "ff": "Fula",
    "gl": "Galician",
    "ka": "Georgian",
    "de": "German",
    "el": "Greek",
    "gn": "Guarani",
    "gu": "Gujarati",
    "ht": "Haitian",
    "ha": "Hausa",
    "he": "Hebrew",
    "hz": "Herero",
    "hi": "Hindi",
    "ho": "Hiri-Motu",
    "hu": "Hungarian",
    "ia": "Interlingua",
    "id": "Indonesian",
    "ie": "Interlingue",
    "ga": "Irish",
    "ig": "Igbo",
    "ik": "Inupiaq",
    "io": "Ido",
    "is": "Icelandic",
    "it": "Italian",
    "iu": "Inuktitut",
    "ja": "Japanese",
    "jv": "Javanese",
    "kl": "Kalaallisut",
    "kn": "Kannada",
    "kr": "Kanuri",
    "ks": "Kashmiri",
    "kk": "Kazakh",
    "km": "Khmer",
    "ki": "Kikuyu",
    "rw": "Kinyarwanda",
    "ky": "Kyrgyz",
    "kv": "Komi",
    "kg": "Kongo",
    "ko": "Korean",
    "ku": "Kurdish",
    "kj": "Kwanyama",
    "la": "Latin",
    "lb": "Luxembourgish",
    "lg": "Luganda",
    "li": "Limburgish",
    "ln": "Lingala",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lu": "Luba-Katanga",
    "lv": "Latvian",
    "gv": "Manx",
    "mk": "Macedonian",
    "mg": "Malagasy",
    "ms": "Malay",
    "ml": "Malayalam",
    "mt": "Maltese",
    "mi": "M\u0101ori",
    "mr": "Marathi",
    "mh": "Marshallese",
    "mn": "Mongolian",
    "na": "Nauru",
    "nv": "Navajo",
    "nb": "Norwegian Bokm\u00e5l",
    "nd": "North-Ndebele",
    "ne": "Nepali",
    "ng": "Ndonga",
    "nn": "Norwegian-Nynorsk",
    "no": "Norwegian",
    "ii": "Nuosu",
    "nr": "South-Ndebele",
    "oc": "Occitan",
    "oj": "Ojibwe",
    "cu": "Old-Church-Slavonic",
    "om": "Oromo",
    "or": "Oriya",
    "os": "Ossetian",
    "pa": "Panjabi",
    "pi": "P\u0101li",
    "fa": "Persian",
    "pl": "Polish",
    "ps": "Pashto",
    "pt": "Portuguese",
    "qu": "Quechua",
    "rm": "Romansh",
    "rn": "Kirundi",
    "ro": "Romanian",
    "ru": "Russian",
    "sa": "Sanskrit",
    "sc": "Sardinian",
    "sd": "Sindhi",
    "se": "Northern-Sami",
    "sm": "Samoan",
    "sg": "Sango",
    "sr": "Serbian",
    "gd": "Scottish-Gaelic",
    "sn": "Shona",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovene",
    "so": "Somali",
    "st": "Southern-Sotho",
    "es": "Spanish",
    "su": "Sundanese",
    "sw": "Swahili",
    "ss": "Swati",
    "sv": "Swedish",
    "ta": "Tamil",
    "te": "Telugu",
    "tg": "Tajik",
    "th": "Thai",
    "ti": "Tigrinya",
    "bo": "Tibetan",
    "tk": "Turkmen",
    "tl": "Tagalog",
    "tn": "Tswana",
    "to": "Tonga",
    "tr": "Turkish",
    "ts": "Tsonga",
    "tt": "Tatar",
    "tw": "Twi",
    "ty": "Tahitian",
    "ug": "Uighur",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "ve": "Venda",
    "vi": "Vietnamese",
    "vo": "Volapuk",
    "wa": "Walloon",
    "cy": "Welsh",
    "wo": "Wolof",
    "fy": "Western-Frisian",
    "xh": "Xhosa",
    "yi": "Yiddish",
    "yo": "Yoruba",
    "za": "Zhuang",
    "zu": "Zulu"
}

class Translate(commands.Cog):
    """ translate text from one language to another """
    def __init__(self, bot):
        self.bot = bot
        self.user_color = discord.Colour(0xed791d) ## orange
        self.mod_color = discord.Colour(0x7289da) ## blurple
        self.db = bot.plugin_db.get_partition(self)
        self.translator = Translator()
        # Auto-translate mapping per thread channel id -> language code
        self.tt = {}
        self.enabled = True
        asyncio.create_task(self._set_config())

    def _serialize_tt(self):
        """Return a copy of self.tt with string keys for MongoDB storage."""
        try:
            return {str(k): v for k, v in (self.tt or {}).items()}
        except Exception:
            return {}

    def _deserialize_tt(self, data):
        """Convert stored auto-translate mapping to use int channel IDs as keys."""
        if isinstance(data, dict):
            out = {}
            for k, v in data.items():
                try:
                    out[int(k)] = v
                except Exception:
                    # Skip keys that cannot be parsed as ints
                    continue
            return out
        if isinstance(data, list):
            # Legacy: list of channel IDs → default to English
            out = {}
            for k in data:
                try:
                    out[int(k)] = 'en'
                except Exception:
                    continue
            return out
        return {}

    def _get_guild_icon(self, guild):
        """Return the guild icon URL or None."""
        if not guild:
            return None
        try:
            return guild.icon.url
        except AttributeError:
            icon = getattr(guild, 'icon', None)
            if icon and hasattr(icon, 'url'):
                return icon.url
            return getattr(guild, 'icon_url', None)
    
    async def _set_config(self):
        """Load persisted settings for this plugin with safe defaults.

        Keys:
        - at-enabled: bool (defaults True) → global toggle for auto-translate
        - auto-translate: dict[channel_id -> lang_code] (or legacy list of channel IDs)
        """
        config = await self.db.find_one({'_id': 'config'}) or {}
        # Prefer new key 'at-enabled'; fall back to legacy 'enabled' if present
        self.enabled = config.get('at-enabled', config.get('enabled', True))
        stored = config.get('auto-translate', {})
        # Normalize to int keys internally
        self.tt = self._deserialize_tt(stored)

    async def _translate_text(self, text, dest=None):
        """Translate text using googletrans; if the method is async, await it.
        Falls back to mtranslate on failure. Returns the translated string.
        """
        try:
            res = self.translator.translate(text, dest=dest) if dest else self.translator.translate(text)
            if asyncio.iscoroutine(res):
                res = await res
            translated = getattr(res, 'text', None)
            if translated is None:
                translated = res if isinstance(res, str) else str(res)
            return translated
        except Exception:
            # Fallback to mtranslate with a safe default
            try:
                code = dest or 'en'
                return translate(text, code)
            except Exception:
                raise


    # +------------------------------------------------------------+
    # |                   Translate cmd                            |
    # +------------------------------------------------------------+
    @commands.group(description='Translate text between languages. Usage: {prefix}tr <language> <text>', aliases=['translate'], invoke_without_command=True)
    async def tr(self, ctx, language: str = None, *, text: str = None):
        """
        🌍 Translate text from one language to another.

        **Usage:**
        `{prefix}tr <language> <text>`
        Example: `{prefix}tr Zulu Hello world!`
        Use `{prefix}tr langs` to see all supported languages.
        """
        if not language or not text:
            usage = f"**Usage:** `{ctx.prefix}{ctx.invoked_with} <language> <text>`\nExample: `{ctx.prefix}{ctx.invoked_with} Spanish Hello!`\nUse `{ctx.prefix}{ctx.invoked_with} langs` for all languages."
            await ctx.send(usage, delete_after=30)
            return

        lang_input = language.strip()
        lang_code = None
        lang_name = None
        # Try to match by code or name (case-insensitive)
        if lang_input.lower() in conv:
            lang_code = lang_input.lower()
            lang_name = conv[lang_code]
        else:
            for code, name in conv.items():
                if lang_input.lower() == name.lower():
                    lang_code = code
                    lang_name = name
                    break

        if not lang_code:
            await ctx.send(f"❌ Unknown language: `{lang_input}`. Use `{ctx.prefix}{ctx.invoked_with} langs` to see all supported languages.", delete_after=20)
            return

        try:
            translated = translate(text, lang_code)
        except Exception as e:
            await ctx.send(f"⚠️ Translation failed: {e}", delete_after=20)
            return

        embed = discord.Embed(color=self.user_color)
        embed.set_author(name=f"{ctx.author.display_name} ({ctx.author.id})", icon_url=getattr(ctx.author, 'avatar_url', None))
        embed.add_field(name="Original", value=f"```{text}```", inline=False)
        embed.add_field(name=f"Translation ({lang_name})", value=f"```{translated}```", inline=False)
        # Use server icon in footer if available
        try:
            guild_icon = ctx.guild.icon.url
        except AttributeError:
            guild_icon = getattr(getattr(ctx.guild, 'icon', None), 'url', None) if ctx.guild else None
            if not guild_icon:
                guild_icon = getattr(ctx.guild, 'icon_url', None) if ctx.guild else None
        embed.set_footer(text="Use {0}tr langs for all languages".format(ctx.prefix), icon_url=guild_icon)
        try:
            await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')
        except discord.Forbidden:
            pass
        await ctx.send(embed=embed)

    # +------------------------------------------------------------+
    # |                Translate plain text                        |
    # +------------------------------------------------------------+
    @commands.command(no_pm=True)
    async def t(self, ctx, language: str = None, *, text: str = None):
        """
        Quick translate: `{prefix}t <language> <text>`
        Example: `{prefix}t French How are you?`
        """
        if not language or not text:
            await ctx.send(f"**Usage:** `{ctx.prefix}t <language> <text>`\nExample: `{ctx.prefix}t French How are you?`", delete_after=20)
            return

        lang_input = language.strip()
        lang_code = None
        for code, name in conv.items():
            if lang_input.lower() == code or lang_input.lower() == name.lower():
                lang_code = code
                break
        if not lang_code:
            await ctx.send(f"❌ Unknown language: `{lang_input}`. Use `{ctx.prefix}tr langs` to see all supported languages.", delete_after=20)
            return
        try:
            await ctx.message.delete()
        except Exception:
            pass
        try:
            translated = translate(text, lang_code)
        except Exception as e:
            await ctx.send(f"⚠️ Translation failed: {e}", delete_after=20)
            return
        if len(translated) > 2000:
            translated = translated[:2000] + "..."
        await ctx.send(translated, delete_after=360)

    # +------------------------------------------------------------+
    # |                   Available Langs                          |
    # +------------------------------------------------------------+
    @tr.command()
    async def langs(self, ctx, page: int = 1):
        """Show all supported languages for translation (sorted, paginated).

        Usage: {prefix}tr langs [page]
        """
        # Sort by language name (value)
        sorted_items = sorted(conv.items(), key=lambda kv: kv[1].lower())  # (code, name)
        per_page = 30
        total_pages = max(1, (len(sorted_items) + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        url = 'https://github.com/lorenzo132/modmail-plugins/blob/master/translate/langs.json'
        guild_icon = self._get_guild_icon(ctx.guild)

        # Build all pages as embeds
        pages = []
        for p in range(1, total_pages + 1):
            start = (p - 1) * per_page
            end = start + per_page
            slice_items = sorted_items[start:end]
            lines = [f"{name} ({code})" for code, name in slice_items]
            body = "\n".join(lines) if lines else "No languages found."

            em = discord.Embed(color=discord.Color.blue())
            em.set_author(name=f'Available Languages (Page {p}/{total_pages})', icon_url=guild_icon)
            em.description = f'```\n{body}```'
            em.set_footer(text=f'Full list: {url}', icon_url=guild_icon)
            pages.append(em)

        # If we have multiple pages and Modmail's paginator is available, use it
        if len(pages) > 1 and PaginatorEmbedInterface is not None:
            try:
                interface = PaginatorEmbedInterface(self.bot, pages, owner=ctx.author)
                await interface.send_to(ctx)
                return
            except Exception:
                # Fallback to page-number approach if paginator API differs
                pass

        # Fallback: send the requested page (or the only page)
        idx = max(1, min(page, total_pages)) - 1
        try:
            await ctx.send(embed=pages[idx])
        except discord.Forbidden:
            # Plain text fallback
            start = idx * per_page
            end = start + per_page
            slice_items = sorted_items[start:end]
            lines = [f"{name} ({code})" for code, name in slice_items]
            body = "\n".join(lines) if lines else "No languages found."
            msg = (
                f'Available languages (Page {idx+1}/{total_pages}):\n```\n{body}```\n{url}\n'
                f'Use `{ctx.prefix}{ctx.invoked_with} langs <page>` to navigate.'
            )
            await ctx.send(msg)

    # +------------------------------------------------------------+
    # |              tr text (subcommand)                         |
    # +------------------------------------------------------------+
    @tr.command(name="text", help="Quickly translate text: tr text <language> <text>")
    async def tr_text(self, ctx, language: str = None, *, text: str = None):
        """Quick translate as a subcommand of tr.

        Usage: {prefix}tr text <language> <text>
        Example: {prefix}tr text French How are you?
        """
        if not language or not text:
            await ctx.send(
                f"**Usage:** `{ctx.prefix}{ctx.invoked_with} text <language> <text>`\n"
                f"Example: `{ctx.prefix}{ctx.invoked_with} text French How are you?`",
                delete_after=20,
            )
            return

        lang_input = language.strip()
        lang_code = None
        for code, name in conv.items():
            if lang_input.lower() == code or lang_input.lower() == name.lower():
                lang_code = code
                break
        if not lang_code:
            await ctx.send(
                f"❌ Unknown language: `{lang_input}`. Use `{ctx.prefix}{ctx.invoked_with} langs` to see all supported languages.",
                delete_after=20,
            )
            return

        try:
            await ctx.message.delete()
        except Exception:
            pass

        try:
            translated = translate(text, lang_code)
        except Exception as e:
            await ctx.send(f"⚠️ Translation failed: {e}", delete_after=20)
            return
        if len(translated) > 2000:
            translated = translated[:2000] + "..."
        await ctx.send(translated, delete_after=360)

    # +------------------------------------------------------------+
    # |           tr message (subcommand)                         |
    # +------------------------------------------------------------+
    @tr.command(name="message", aliases=["msg"], help="Translate the provided message content into English.")
    async def tr_message(self, ctx, *, message):
        """Translate a given message string into English.

        Usage: {prefix}tr message <text>
        """
        tmsg = await self._translate_text(message, dest='en')
        em = discord.Embed()
        em.color = 4388013
        em.description = tmsg
        await ctx.channel.send(embed=em)

    # +------------------------------------------------------------+
    # |           tr messageid (subcommand)                        |
    # +------------------------------------------------------------+
    @tr.command(name="messageid", aliases=["mid", "msgid"], help="Translate a message in this thread by its ID. Usage: tr messageid <id> [language]")
    async def tr_messageid(self, ctx, message_id: int, language: str = 'en'):
        """Translate the content of a message in this thread by ID.

        Usage:
          {prefix}tr messageid <message_id> [language]
        Defaults to English when language isn't provided.
        """
        # Ensure we are in a Modmail thread to avoid CheckFailure and provide a helpful error
        topic = getattr(ctx.channel, 'topic', '') or ''
        if 'User ID:' not in topic:
            await ctx.send("This command must be used inside a Modmail thread channel.", delete_after=15)
            return
        # Try to fetch the message from the current channel (thread)
        try:
            msg = await ctx.channel.fetch_message(message_id)
        except Exception:
            await ctx.send("❌ Couldn't find a message with that ID in this channel.", delete_after=15)
            return

        # Extract text: prefer embed description (Modmail relays), else content
        text = None
        if msg.embeds and getattr(msg.embeds[0], 'description', None):
            text = msg.embeds[0].description
        elif msg.content:
            text = msg.content
        if not text:
            await ctx.send("⚠️ That message has no textual content to translate.", delete_after=15)
            return

        lang_code = self._resolve_lang_code(language or 'en')
        try:
            translated = await self._translate_text(text, dest=lang_code)
        except Exception as e:
            await ctx.send(f"⚠️ Translation failed: {e}", delete_after=15)
            return

        em = discord.Embed(color=4388013)
        em.add_field(name="Original", value=text if len(text) < 1000 else text[:1000] + '…', inline=False)
        em.add_field(name=f"Translated ({conv.get(lang_code, lang_code)})", value=translated if len(translated) < 1000 else translated[:1000] + '…', inline=False)
        guild_icon = self._get_guild_icon(ctx.guild)
        em.set_footer(text="Translated via message ID", icon_url=guild_icon)
        await ctx.channel.send(embed=em)

    # +------------------------------------------------------------+
    # |     tr auto-thread & tr toggle-auto (subcommands)         |
    # +------------------------------------------------------------+
    @tr.command(name="auto-thread", help="Add/remove this thread to the auto-translate list.")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def tr_auto_thread(self, ctx):
        """Toggle auto-translate for the current thread (subcommand wrapper)."""
        await self.auto_translate_thread(ctx)

    @tr.command(name="toggle-auto", help="Enable or disable auto-translate globally for this plugin.")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def tr_toggle_auto(self, ctx, enabled: bool):
        """Toggle global auto-translate on/off (subcommand wrapper)."""
        await self.toggle_auto_translations(ctx, enabled)

    # +------------------------------------------------------------+
    # |              Translate Message with ID                     |
    # +------------------------------------------------------------+
    @commands.command(aliases=["tt"])
    async def translatetext(self, ctx, *, message):
        """
        Translates given messageID into English
        """
        tmsg = await self._translate_text(message, dest='en')
        em = discord.Embed()
        em.color = 4388013
        em.description = tmsg
        # Footer small icon = server icon
        try:
            guild_icon = ctx.guild.icon.url
        except AttributeError:
            guild_icon = getattr(getattr(ctx.guild, 'icon', None), 'url', None) if ctx.guild else None
            if not guild_icon:
                guild_icon = getattr(ctx.guild, 'icon_url', None) if ctx.guild else None
        em.set_footer(text="Translated to English", icon_url=guild_icon)
        await ctx.channel.send(embed=em)

    # +------------------------------------------------------------+
    # |                 Auto Translate Text                        |
    # +------------------------------------------------------------+
    @commands.command(aliases=["att"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def auto_translate_thread(self, ctx, language: str = None):
        """Enable/disable per-thread auto-translate and set target language.

        Usage:
          {prefix}att <language>   -> Enable/update auto-translate to language (e.g. English)
          {prefix}att off          -> Disable auto-translate for this thread
        """
        if "User ID:" not in ctx.channel.topic:
            await ctx.send("The Channel Is Not A Modmail Thread")
            return

        ch_id = ctx.channel.id
        # Disable keywords
        if language and language.lower() in {"off", "disable", "disabled", "false", "none"}:
            if ch_id in self.tt:
                self.tt.pop(ch_id, None)
                await self.db.update_one({'_id': 'config'}, {'$set': {'auto-translate': self._serialize_tt()}}, upsert=True)
                await ctx.send("Removed channel from Auto Translations list.")
            else:
                await ctx.send("Auto Translations were not enabled for this thread.")
            return

        if not language:
            # Toggle behavior if no language passed
            if ch_id in self.tt:
                self.tt.pop(ch_id, None)
                await self.db.update_one({'_id': 'config'}, {'$set': {'auto-translate': self._serialize_tt()}}, upsert=True)
                await ctx.send("Removed channel from Auto Translations list.")
            else:
                # Default to English if enabling without a language
                self.tt[ch_id] = 'en'
                await self.db.update_one({'_id': 'config'}, {'$set': {'auto-translate': self._serialize_tt()}}, upsert=True)
                await ctx.send("Added channel to Auto Translations list. Language set to English.")
            return

        # Resolve language to code
        lang_input = language.strip()
        lang_code = None
        for code, name in conv.items():
            if lang_input.lower() == code or lang_input.lower() == name.lower():
                lang_code = code
                break
        if not lang_code:
            await ctx.send(f"❌ Unknown language: `{lang_input}`. Use `{ctx.prefix}tr langs` to see all supported languages.", delete_after=20)
            return

        # Enable/update mapping
        self.tt[ch_id] = lang_code
        await self.db.update_one({'_id': 'config'}, {'$set': {'auto-translate': self._serialize_tt()}}, upsert=True)
        await ctx.send(f"Auto-translate enabled for this thread → {conv[lang_code]} ({lang_code}).")
    
    # +------------------------------------------------------------+
    # |              Toggle Auto Translate on/off                  |
    # +------------------------------------------------------------+
    @commands.command(aliases=["tat"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def toggle_auto_translations(self, ctx, enabled: bool):
        """to be used inside ticket threads"""
        self.enabled = enabled
        await self.db.update_one(
            {'_id': 'config'},
            {'$set': {'at-enabled': self.enabled}}, 
            upsert=True
            )
        await ctx.send(f"{'Enabled' if enabled else 'Disabled'} Auto Translations")

    # +------------------------------------------------------------+
    # |       Translate and reply helpers/commands                |
    # +------------------------------------------------------------+
    def _resolve_lang_code(self, lang: str, default: str = 'en') -> str:
        if not lang:
            return default
        lang_input = lang.strip()
        for code, name in conv.items():
            if lang_input.lower() == code or lang_input.lower() == name.lower():
                return code
        return default

    async def _invoke_reply(self, ctx, text: str, anonymous: bool = False):
        """Invoke Modmail's reply/anonreply command as the invoker."""
        cmd = None
        if anonymous:
            cmd = ctx.bot.get_command('anonreply') or ctx.bot.get_command('ar') or ctx.bot.get_command('areply')
        else:
            cmd = ctx.bot.get_command('reply') or ctx.bot.get_command('r')
        if not cmd:
            # Fallback: just send to channel (will be relayed by Modmail in most setups)
            await ctx.send(text)
            return
        await ctx.invoke(cmd, message=text)

    @commands.command(name='attr')
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def auto_translate_and_reply(self, ctx, language: str, *, message: str):
        """Translate a message then reply to the user with only the translation.

        Also posts an internal embed (bot message) showing Original and Translated for staff.

        Usage: {prefix}attr <language> <message>
        Example: {prefix}attr English Hello, how are you?
        """
        lang_code = self._resolve_lang_code(language)
        translated = translate(message, lang_code)

        # Send internal embed for staff (bot message, typically not relayed)
        em = discord.Embed(color=self.mod_color)
        em.set_author(name=f"Translate & Reply → {conv.get(lang_code, lang_code)}")
        em.add_field(name="Original", value=f"```{message}```", inline=False)
        em.add_field(name=f"Translated ({conv.get(lang_code, lang_code)})", value=f"```{translated}```", inline=False)
        guild_icon = self._get_guild_icon(ctx.guild)
        em.set_footer(text="attr", icon_url=guild_icon)
        try:
            await ctx.send(embed=em)
        except discord.Forbidden:
            await ctx.send(f"Original:\n```{message}```\nTranslated ({conv.get(lang_code, lang_code)}):\n```{translated}```")

        # Send translated message to user via reply
        await self._invoke_reply(ctx, translated, anonymous=False)

    @commands.command(name='trr')
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def translate_reply(self, ctx, language_or_message: str = None, *, message: str = None):
        """Translate then reply. Language optional (defaults to English).

        Usage:
          {prefix}trr <language> <message>
          {prefix}trr <message>              (defaults to English)
        """
        if message is None and language_or_message is not None:
            # Assume first arg is actually the message
            language = 'en'
            message = language_or_message
        else:
            language = language_or_message or 'en'
        lang_code = self._resolve_lang_code(language)
        translated = translate(message, lang_code)
        await self._invoke_reply(ctx, translated, anonymous=False)

    @commands.command(name='trar')
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def translate_anonreply(self, ctx, language_or_message: str = None, *, message: str = None):
        """Translate then anon-reply. Language optional (defaults to English).

        Usage:
          {prefix}trar <language> <message>
          {prefix}trar <message>            (defaults to English)
        """
        if message is None and language_or_message is not None:
            language = 'en'
            message = language_or_message
        else:
            language = language_or_message or 'en'
        lang_code = self._resolve_lang_code(language)
        translated = translate(message, lang_code)
        await self._invoke_reply(ctx, translated, anonymous=True)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if not self.enabled:
            return
        
        channel = message.channel

        if channel.id not in self.tt:
            return
        
        if isinstance(message.author,User):
            return
        
        if "User ID:" not in channel.topic:
            return
        
        if not message.embeds:
            return
        
        # Avoid translating our own auto-translate embeds or bot help/command embeds
        emb0 = message.embeds[0]
        footer_text = getattr(getattr(emb0, 'footer', None), 'text', '') or ''
        if footer_text.strip() == 'Auto Translate Plugin':
            return
        if message.author.id == getattr(self.bot.user, 'id', None):
            # Heuristic: help/command embeds usually contain these tokens
            parts = []
            title = getattr(emb0, 'title', None)
            desc = getattr(emb0, 'description', None)
            if title:
                parts.append(title)
            if desc:
                parts.append(desc)
            for f in getattr(emb0, 'fields', []) or []:
                try:
                    parts.append((f.name or ''))
                    parts.append((f.value or ''))
                except Exception:
                    pass
            blob = ' '.join(parts)
            if any(token in blob for token in ['Usage:', 'Permission level', 'Aliases:', 'Example:', 'Examples:']):
                return

        msg = emb0.description
        if not msg:
            return
        # Translate to the configured language code for this thread
        lang_code = self.tt.get(channel.id, 'en')
        translated = await self._translate_text(msg, dest=lang_code)
        em = discord.Embed()
        em.add_field(name="Original", value=msg if len(msg) < 1000 else msg[:1000] + '…', inline=False)
        em.add_field(name=f"Translated ({conv.get(lang_code, lang_code)})", value=translated if len(translated) < 1000 else translated[:1000] + '…', inline=False)
        em.color = 4388013
        # Footer small icon = server icon
        try:
            guild_icon = channel.guild.icon.url
        except AttributeError:
            guild_icon = getattr(getattr(channel.guild, 'icon', None), 'url', None) if getattr(channel, 'guild', None) else None
            if not guild_icon:
                guild_icon = getattr(channel.guild, 'icon_url', None) if getattr(channel, 'guild', None) else None
        em.set_footer(text="Auto Translate Plugin", icon_url=guild_icon)

        await channel.send(embed=em)


async def setup(bot):
    await bot.add_cog(Translate(bot))
