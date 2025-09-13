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
        self.tt = set()
        self.enabled = True
        asyncio.create_task(self._set_config())
    
    async def _set_config(self):  # exception=AttributeError("'NoneType' object has no attribute 'get'")>
        try:
            config = await self.db.find_one({'_id': 'config'})
            self.enabled = config.get('enabled', True)
            self.tt = set(config.get('auto-translate', []))  # AttributeError: 'NoneType' object has no attribute 'get'
        except:
            pass


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
        start = (page - 1) * per_page
        end = start + per_page
        slice_items = sorted_items[start:end]

        lines = [f"{name} ({code})" for code, name in slice_items]
        body = "\n".join(lines) if lines else "No languages found."

        url = 'https://github.com/lorenzo132/modmail-plugins/blob/master/translate/langs.json'
        em = discord.Embed(color=discord.Color.blue())
        # Small icon = server icon
        try:
            guild_icon = ctx.guild.icon.url
        except AttributeError:
            guild_icon = getattr(getattr(ctx.guild, 'icon', None), 'url', None) if ctx.guild else None
            if not guild_icon:
                guild_icon = getattr(ctx.guild, 'icon_url', None) if ctx.guild else None
        em.set_author(name=f'Available Languages (Page {page}/{total_pages})', icon_url=guild_icon)
        em.description = f'```\n{body}```'
        em.set_footer(text=f'Full list: {url}', icon_url=guild_icon)
        try:
            await ctx.send(embed=em)
        except discord.Forbidden:
            msg = f'Available languages (Page {page}/{total_pages}):\n```\n{body}```\n{url}'
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
        tmsg = self.translator.translate(message)
        em = discord.Embed()
        em.color = 4388013
        em.description = tmsg.text
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
        original command by officialpiyush
        """
        tmsg = self.translator.translate(message)
        em = discord.Embed()
        em.color = 4388013
        em.description = tmsg.text
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
    async def auto_translate_thread(self, ctx):
        """ to be used inside ticket threads
        original command by officialpiyush
        """
        if "User ID:" not in ctx.channel.topic:
            await ctx.send("The Channel Is Not A Modmail Thread")
            return

        if ctx.channel.id in self.tt:
            self.tt.remove(ctx.channel.id)
            removed = True

        else:
            self.tt.add(ctx.channel.id)
            removed = False
        
        await self.db.update_one(
            {'_id': 'config'},
            {'$set': {'auto-translate': list(self.tt)}}, 
            upsert=True
            )

        await ctx.send(f"{'Removed' if removed else 'Added'} Channel {'from' if removed else 'to'} Auto Translations List.")
    
    # +------------------------------------------------------------+
    # |              Toggle Auto Translate on/off                  |
    # +------------------------------------------------------------+
    @commands.command(aliases=["tat"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def toggle_auto_translations(self, ctx, enabled: bool):
        """ to be used inside ticket threads
        original command by officialpiyush
        """
        self.enabled = enabled
        await self.db.update_one(
            {'_id': 'config'},
            {'$set': {'at-enabled': self.enabled}}, 
            upsert=True
            )
        await ctx.send(f"{'Enabled' if enabled else 'Disabled'} Auto Translations")
    
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
        
        msg = message.embeds[0].description
        tmsg = self.translator.translate(msg)
        em = discord.Embed()
        em.description = tmsg.text
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
