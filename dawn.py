import asyncio
import json
import re
import os
from datetime import datetime, timezone

from aiohttp import ClientSession, ClientTimeout, BasicAuth
from aiohttp_socks import ProxyConnector
from fake_useragent import FakeUserAgent
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.panel import Panel
from rich.align import Align


class Dawn:
    def __init__(self) -> None:
        self.BASE_API = "https://api.dawninternet.com"
        self.HEADERS = {}
        self.proxies = []
        self.proxy_index = 0
        self.account_proxies = {}
        self.user_ids = {}
        self.session_tokens = {}
        self.console = Console()
        self.account_states = {}

    # ---------------- Box-style UI ----------------
    def show_intro(self):
        project_info = Panel.fit(
            Align.center("Dawn Farming Tool\npowered by Forest Army", vertical="middle"),
            title="Project Info",
            border_style="cyan",
            padding=(1, 4)
        )

        features = Panel.fit(
            "\n".join([
                "• Automated Farming",
                "• Multi-Account Support",
                "• Proxy Support (With Rotation)",
                "• Live Status Dashboard"
            ]),
            title="Features",
            border_style="green",
            padding=(1, 4)
        )

        proxy_config = Panel.fit(
            "\n".join([
                "1. Run With Proxy",
                "2. Run Without Proxy"
            ]),
            title="Proxy Configuration",
            border_style="magenta",
            padding=(1, 6)
        )

        self.console.print(project_info)
        self.console.print(features)
        self.console.print(proxy_config)

    def ask_proxy_choice(self):
        choice = self.console.input("[bold blue]Choose [1/2] -> [/bold blue]").strip()
        while choice not in ["1", "2"]:
            choice = self.console.input("[bold blue]Choose [1/2] -> [/bold blue]").strip()

        rotate_proxy = False
        if choice == "1":
            rotate_panel = Panel.fit(
                "\n".join([
                    "Rotate Proxy on Failure?",
                    "[y] Yes",
                    "[n] No"
                ]),
                title="Proxy Rotation",
                border_style="yellow",
                padding=(1, 6)
            )
            self.console.print(rotate_panel)
            rotate = self.console.input("[bold yellow]Choose [y/n] -> [/bold yellow]").strip().lower()
            while rotate not in ["y", "n"]:
                rotate = self.console.input("[bold yellow]Choose [y/n] -> [/bold yellow]").strip().lower()
            rotate_proxy = (rotate == "y")

        return int(choice), rotate_proxy
    # ----------------------------------------------

    def format_seconds(self, seconds: int) -> str:
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    # ---------------- Dashboard ----------------
    def generate_table(self) -> Table:
        table = Table(
            title="Dawn Auto Farming BOT → powered by : Forest Army",
            expand=True,
            border_style="cyan"
        )
        table.add_column("ACCOUNT", justify="left", style="white", no_wrap=True, width=25)
        table.add_column("PROXY", justify="left", style="magenta", width=20)
        table.add_column("POINTS", justify="center", style="yellow", width=15)
        table.add_column("PING STATUS", justify="center", style="blue", width=20)
        table.add_column("STATUS", justify="left", style="green")

        for email in self.user_ids.keys():
            state = self.account_states.get(email, {})
            masked_email = self.mask_account(email)
            proxy = state.get('proxy', 'N/A') or 'N/A'
            points = str(state.get('points', 'N/A'))
            ping_status = state.get('ping_status', 'Queued')
            status_text = state.get('status', 'Initializing...')

            status_style = "white"
            if "failed" in status_text.lower() or "error" in status_text.lower():
                status_style = "bold red"
            elif "success" in status_text.lower() or "running" in status_text.lower():
                status_style = "bold green"
            elif any(s in status_text.lower() for s in ["checking", "fetching", "sending"]):
                status_style = "yellow"

            table.add_row(
                masked_email,
                proxy,
                points,
                ping_status,
                Text(status_text, style=status_style)
            )
        return table

    def update_status(self, email: str, **kwargs):
        if email in self.account_states:
            self.account_states[email].update(kwargs)
    # ----------------------------------------------

    def load_accounts(self):
        filename = "tokens.json"
        try:
            if not os.path.exists(filename):
                return []
            with open(filename, 'r') as file:
                data = json.load(file)
                return data if isinstance(data, list) else []
        except:
            return []

    async def load_proxies(self):
        filename = "proxy.txt"
        try:
            if not os.path.exists(filename):
                return
            with open(filename, 'r') as f:
                self.proxies = [line.strip() for line in f.read().splitlines() if line.strip()]
        except:
            self.proxies = []

    def check_proxy_schemes(self, proxy):
        schemes = ["http://", "https://", "socks4://", "socks5://"]
        return proxy if any(proxy.startswith(scheme) for scheme in schemes) else f"http://{proxy}"

    def get_next_proxy_for_account(self, account):
        if not self.proxies: return None
        if account not in self.account_proxies:
            proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
            self.account_proxies[account] = proxy
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return self.account_proxies[account]

    def rotate_proxy_for_account(self, account):
        if not self.proxies: return None
        proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
        self.account_proxies[account] = proxy
        self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return proxy

    def build_proxy_config(self, proxy=None):
        if not proxy: return None, None, None
        if proxy.startswith("socks"): return ProxyConnector.from_url(proxy), None, None
        if proxy.startswith("http"):
            if match := re.match(r"http://(.*?):(.*?)@(.*)", proxy):
                username, password, host_port = match.groups()
                return None, f"http://{host_port}", BasicAuth(username, password)
            return None, proxy, None
        return None, None, None

    def mask_account(self, account):
        if "@" in account:
            local, domain = account.split('@', 1)
            return f"{local[:3]}***{local[-3:]}@{domain}"
        return f"{account[:3]}***{account[-3:]}"

    # ---------------- Core Functions ----------------
    async def check_connection(self, proxy_url=None):
        connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
        try:
            async with ClientSession(connector=connector, timeout=ClientTimeout(total=10)) as session:
                async with session.get("https://api.ipify.org?format=json", proxy=proxy, proxy_auth=proxy_auth) as response:
                    response.raise_for_status()
                    return True
        except:
            return False

    async def user_point(self, email: str, proxy_url=None):
        url = f"{self.BASE_API}/point?user_id={self.user_ids[email]}"
        headers = {**self.HEADERS[email], "Authorization": f"Bearer {self.session_tokens[email]}"}
        connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
        try:
            async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as s:
                async with s.get(url, headers=headers, proxy=proxy, proxy_auth=proxy_auth) as resp:
                    if resp.status == 401: return False, "Token Expired"
                    resp.raise_for_status()
                    data = await resp.json()
                    return True, data.get("points", 0)
        except:
            return False, "Error"

    async def extension_ping(self, email: str, proxy_url=None, max_retries=3):
        url = f"{self.BASE_API}/ping?role=extension"
        data = json.dumps({
            "user_id": self.user_ids[email],
            "extension_id": "fpdkjdnhkakefebpekbdhillbhonfjjp",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        })
        headers = {**self.HEADERS[email], "Content-Type": "application/json", "Authorization": f"Bearer {self.session_tokens[email]}"}

        for attempt in range(max_retries):
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as s:
                    async with s.post(url, headers=headers, data=data, proxy=proxy, proxy_auth=proxy_auth) as resp:
                        if resp.status == 401: return False, "Token Expired"
                        if resp.status == 429:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(60)
                                continue
                            return False, "HTTP 429"
                        resp.raise_for_status()
                        return True, (await resp.json()).get("message", "OK")
            except:
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
                return False, "Request Failed"
        return False, "Max retries exceeded"

    async def process_user_earning(self, email: str, use_proxy: bool):
        while True:
            proxy = self.get_next_proxy_for_account(email) if use_proxy else None
            self.update_status(email, status="Fetching Points...")
            success, result = await self.user_point(email, proxy)
            self.update_status(email, points=result if success else "Error", status="Running" if success else "Point fetch failed")
            await asyncio.sleep(300)

    async def process_send_keepalive(self, email: str, use_proxy: bool):
        while True:
            proxy = self.get_next_proxy_for_account(email) if use_proxy else None
            self.update_status(email, status="Sending Ping...")
            success, message = await self.extension_ping(email, proxy)

            if success:
                self.update_status(email, ping_status=message)
                for i in range(600, 0, -1):
                    self.update_status(email, status=f"Next Ping in {self.format_seconds(i)}")
                    await asyncio.sleep(1)
            else:
                self.update_status(email, ping_status="Failed", status=f"Error: {message}")
                await asyncio.sleep(60)

    async def process_account(self, email: str, use_proxy: bool, rotate_proxy: bool):
        proxy = self.get_next_proxy_for_account(email) if use_proxy else None
        self.update_status(email, proxy=proxy, status="Checking Connection...")
        while not await self.check_connection(proxy):
            self.update_status(email, status="Connection Failed. Retrying...")
            if rotate_proxy:
                proxy = self.rotate_proxy_for_account(email)
                self.update_status(email, proxy=proxy)
            await asyncio.sleep(5)

        self.update_status(email, status="Connection Successful")
        await asyncio.gather(
            self.process_user_earning(email, use_proxy),
            self.process_send_keepalive(email, use_proxy)
        )

    async def main(self):
        accounts = self.load_accounts()
        if not accounts: return

        self.show_intro()
        proxy_choice, rotate_proxy = self.ask_proxy_choice()
        os.system('cls' if os.name == 'nt' else 'clear')
        use_proxy = proxy_choice == 1

        if use_proxy:
            await self.load_proxies()

        coroutines = []
        for account in accounts:
            if not (email := account.get("email")) or not (uid := account.get("userId")) or not (token := account.get("sessionToken")):
                continue
            self.user_ids[email], self.session_tokens[email] = uid, token
            self.HEADERS[email] = {"User-Agent": FakeUserAgent().random}
            self.account_states[email] = {}
            coroutines.append(self.process_account(email, use_proxy, rotate_proxy))

        if not coroutines:
            return

        tasks = [asyncio.create_task(coro) for coro in coroutines]

        with Live(self.generate_table(), console=self.console, screen=True, auto_refresh=False) as live:
            while any(not t.done() for t in tasks):
                live.update(self.generate_table(), refresh=True)
                await asyncio.sleep(0.5)
            live.update(self.generate_table(), refresh=True)


if __name__ == "__main__":
    try:
        bot = Dawn()
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        pass
    except:
        pass
