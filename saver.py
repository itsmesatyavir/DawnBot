import asyncio
import json
import os
import re
import uuid
from datetime import datetime

import pytz
from aiohttp import (BasicAuth, ClientResponseError, ClientSession,
                     ClientTimeout)
from aiohttp_socks import ProxyConnector
from fake_useragent import FakeUserAgent
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

wib = pytz.timezone('Asia/Kolkata')

class Dawn:
    def __init__(self) -> None:
        self.console = Console()
        self.BASE_API = "https://api.dawninternet.com"
        self.PRIVY_API = "https://auth.privy.io/api/v1"
        self.REF_CODE = "B8CQG4CW"
        self.BASE_HEADERS = {}
        self.PRIVY_HEADERS = {}
        self.proxies = []
        self.proxy_index = 0
        self.account_proxies = {}

    def clear_terminal(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def _log_status(self, title: str, message: str, style: str):
        self.console.print(Panel(Text(message, justify="center"), title=f"[bold]{title}[/bold]", border_style=style))

    def welcome(self):
        project_info = Text("Dawn Login Tool\npowered by Forest Army\nhttps://t.me/forestarmy", justify="center")
        self.console.print(Panel(project_info, title="[bold cyan]Project Info[/bold cyan]", border_style="green", expand=False))
        features = (
            "• Automated Login/Registration\n"
            "• OTP Handling\n"
            "• Proxy Support (With Rotation)\n"
            "• Auto-Save Tokens to tokens.json"
        )
        self.console.print(Panel(features, title="[bold cyan]Features[/bold cyan]", border_style="magenta", expand=False))

    def format_seconds(self, seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
        
    def save_tokens(self, new_accounts):
        filename = "tokens.json"
        try:
            existing_accounts = []
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                with open(filename, 'r') as file:
                    try:
                        existing_accounts = json.load(file)
                    except json.JSONDecodeError:
                        pass
            account_dict = {acc["email"]: acc for acc in existing_accounts}
            for new_acc in new_accounts:
                account_dict[new_acc["email"]] = new_acc
            with open(filename, 'w') as file:
                json.dump(list(account_dict.values()), file, indent=4)
            self._log_status("Save Tokens", "Tokens saved successfully to tokens.json", "green")
        except Exception as e:
            self._log_status("Save Tokens", f"Failed to save tokens: {e}", "red")

    async def load_proxies(self):
        filename = "proxy.txt"
        try:
            if not os.path.exists(filename):
                self._log_status("Load Proxies", "File 'proxy.txt' not found.", "red")
                return
            with open(filename, 'r') as f:
                self.proxies = [line.strip() for line in f.read().splitlines() if line.strip()]
            if not self.proxies:
                self._log_status("Load Proxies", "No proxies found in 'proxy.txt'.", "yellow")
                return
            self._log_status("Load Proxies", f"Total proxies loaded: {len(self.proxies)}", "green")
        except Exception as e:
            self._log_status("Load Proxies", f"Failed to load proxies: {e}", "red")
            self.proxies = []

    def check_proxy_schemes(self, proxies):
        schemes = ["http://", "https://", "socks4://", "socks5://"]
        return proxies if any(proxies.startswith(scheme) for scheme in schemes) else f"http://{proxies}"

    def get_next_proxy_for_account(self, account):
        if not self.proxies:
            return None
        if account not in self.account_proxies:
            proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
            self.account_proxies[account] = proxy
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return self.account_proxies.get(account)

    def rotate_proxy_for_account(self, account):
        if not self.proxies:
            return None
        proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
        self.account_proxies[account] = proxy
        self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return proxy
    
    def build_proxy_config(self, proxy=None):
        if not proxy:
            return None, None, None
        if proxy.startswith("socks"):
            return ProxyConnector.from_url(proxy), None, None
        elif proxy.startswith("http"):
            match = re.match(r"http://(.*?):(.*?)@(.*)", proxy)
            if match:
                username, password, host_port = match.groups()
                return None, f"http://{host_port}", BasicAuth(username, password)
            else:
                return None, proxy, None
        raise Exception("Unsupported Proxy Type.")
    
    def mask_account(self, account):
        if "@" in account:
            local, domain = account.split('@', 1)
            return f"{local[:3]}***{local[-3:]}@{domain}"
        return account

    def print_question(self):
        options = Text("1. Run With Proxy\n2. Run Without Proxy", justify="center")
        self.console.print(Panel(options, title="[bold yellow]Proxy Configuration[/bold yellow]", border_style="yellow"))
        while True:
            try:
                proxy_choice = int(self.console.input("[bold blue]Choose [1/2] -> [/bold blue]"))
                if proxy_choice in [1, 2]:
                    break
                else:
                    self._log_status("Input Error", "Please enter either 1 or 2.", "red")
            except ValueError:
                self._log_status("Input Error", "Invalid input. Please enter a number.", "red")
        rotate_proxy = False
        if proxy_choice == 1:
            self.console.print(Panel("Rotate proxy if a connection fails?", title="[bold yellow]Proxy Rotation[/bold yellow]", border_style="yellow"))
            while True:
                choice = self.console.input("[bold blue]Rotate Invalid Proxy? [y/n] -> [/bold blue]").strip().lower()
                if choice in ["y", "n"]:
                    rotate_proxy = choice == "y"
                    break
                else:
                    self._log_status("Input Error", "Invalid input. Please enter 'y' or 'n'.", "red")
        return proxy_choice, rotate_proxy
    
    async def _api_call(self, session_method, url, action_name, **kwargs):
        retries = 5
        for attempt in range(retries):
            try:
                async with session_method(url=url, **kwargs) as response:
                    response.raise_for_status()
                    result = await response.json()
                    self._log_status(action_name, "Request successful", "green")
                    return result
            except ClientResponseError as e:
                if e.status == 400 and action_name == "Use Referral":
                    self._log_status(action_name, "Referral already used or invalid.", "yellow")
                    return None
                self._log_status(action_name, f"Failed with status {e.status}: {e.message}", "red")
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                else:
                    return None
            except Exception as e:
                self._log_status(action_name, f"An error occurred: {e}", "red")
                if attempt < retries - 1:
                    self._log_status(action_name, f"Retrying... ({attempt + 1}/{retries})", "yellow")
                    await asyncio.sleep(5)
                else:
                    return None
        return None

    async def check_connection(self, proxy_url=None):
        connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
        try:
            async with ClientSession(connector=connector, timeout=ClientTimeout(total=10)) as session:
                async with session.get("https://api.ipify.org?format=json", proxy=proxy, proxy_auth=proxy_auth) as response:
                    response.raise_for_status()
                    self._log_status("Check Connection", "Connection OK", "green")
                    return True
        except Exception as e:
            self._log_status("Check Connection", f"Connection failed: {e}", "red")
            return None

    async def process_accounts(self, email: str, use_proxy: bool, rotate_proxy: bool):
        proxy = self.get_next_proxy_for_account(email) if use_proxy else None
        is_connected = await self.check_connection(proxy)
        if not is_connected:
            if rotate_proxy:
                self._log_status("Proxy", "Connection failed, rotating proxy...", "yellow")
                proxy = self.rotate_proxy_for_account(email)
                if not await self.check_connection(proxy):
                    self._log_status("Process Account", "Connection check failed after rotating proxy.", "red")
                    return
            else:
                self._log_status("Process Account", "Connection check failed.", "red")
                return
        connector, proxy_url, proxy_auth = self.build_proxy_config(proxy)
        async with ClientSession(connector=connector) as session:
            data = json.dumps({"email": email})
            headers = {**self.PRIVY_HEADERS[email], "Content-Length": str(len(data)), "Content-Type": "application/json"}
            if not await self._api_call(session.post, f"{self.PRIVY_API}/passwordless/init", "Request OTP", data=data, headers=headers, proxy=proxy_url, proxy_auth=proxy_auth):
                return
        self.console.print(Panel("An OTP has been sent to your email.", title="[bold blue]OTP Input[/bold blue]", border_style="blue"))
        otp_code = self.console.input("[bold blue]Enter OTP Code -> [/bold blue]")
        async with ClientSession(connector=connector) as session:
            data = json.dumps({"email": email, "code": otp_code, "mode": "login-or-sign-up"})
            headers = {**self.PRIVY_HEADERS[email], "Content-Length": str(len(data)), "Content-Type": "application/json"}
            auth_response = await self._api_call(session.post, f"{self.PRIVY_API}/passwordless/authenticate", "Authenticate OTP", data=data, headers=headers, proxy=proxy_url, proxy_auth=proxy_auth)
            if not auth_response: return
        privy_token = auth_response.get("token")
        if not privy_token:
            self._log_status("Process Account", "No token received from authentication.", "red")
            return
        async with ClientSession(connector=connector) as session:
            headers = {**self.BASE_HEADERS[email], "X-Privy-Token": privy_token}
            jwt_response = await self._api_call(session.get, f"{self.BASE_API}/auth?jwt=true&role=extension", "JWT Authentication", headers=headers, proxy=proxy_url, proxy_auth=proxy_auth)
            if not jwt_response: return
        user_id = jwt_response.get("user", {}).get("id")
        session_token = jwt_response.get("session_token")
        if user_id and session_token:
            async with ClientSession(connector=connector) as session:
                data = json.dumps({"referralCode": self.REF_CODE})
                headers = {**self.BASE_HEADERS[email], "Authorization": f"Bearer {session_token}", "Content-Length": str(len(data)), "Content-Type": "application/json"}
                await self._api_call(session.post, f"{self.BASE_API}/referral/use", "Use Referral", data=data, headers=headers, proxy=proxy_url, proxy_auth=proxy_auth)
            account_data = [{"email": email, "userId": user_id, "sessionToken": session_token}]
            self.save_tokens(account_data)
            self._log_status("Process Account", f"Account {self.mask_account(email)} processed successfully!", "green")
        else:
            self._log_status("Process Account", "Invalid response data from JWT auth.", "red")
    
    async def main(self):
        try:
            self.clear_terminal()
            self.welcome()
            with open('emails.txt', 'r') as file:
                emails = [line.strip() for line in file if line.strip()]
            if not emails:
                self._log_status("File Loading", "No emails found in 'emails.txt'.", "red")
                return
            proxy_choice, rotate_proxy = self.print_question()
            use_proxy = proxy_choice == 1
            if use_proxy:
                await self.load_proxies()
            for idx, email in enumerate(emails, start=1):
                self.console.rule(f"[bold blue]Processing Account {idx} of {len(emails)}[/bold blue]")
                if "@" not in email:
                    self._log_status("Email Validation", f"Skipping invalid email: {email}", "yellow")
                    continue
                user_agent = FakeUserAgent().random
                self.BASE_HEADERS[email] = {
                    "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9", "Origin": "chrome-extension://fpdkjdnhkakefebpekbdhillbhonfjjp",
                    "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "cross-site", "User-Agent": user_agent
                }
                self.PRIVY_HEADERS[email] = {
                    "Accept": "application/json", "Accept-Language": "en-US,en;q=0.9", "Origin": "chrome-extension://fpdkjdnhkakefebpekbdhillbhonfjjp",
                    "Privy-App-Id": "cmfb724md0057la0bs4tg0vf1", "Privy-Ca-Id": str(uuid.uuid4()), "Privy-Client": "react-auth:2.24.0",
                    "Privy-Ui": "t", "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "none",
                    "Sec-Fetch-Storage-Access": "active", "User-Agent": user_agent
                }
                self._log_status("Account", f"Email: {self.mask_account(email)}", "cyan")
                proxy_in_use = self.get_next_proxy_for_account(email) if use_proxy else 'N/A'
                self._log_status("Proxy", f"Using Proxy: {proxy_in_use}", "cyan")
                await self.process_accounts(email, use_proxy, rotate_proxy)
                if idx < len(emails):
                   self._log_status("Cooldown", "Waiting 3 seconds before next account...", "magenta")
                   await asyncio.sleep(3)
            self.console.rule("[bold green]All accounts processed![/bold green]")
        except FileNotFoundError:
            self._log_status("File Loading", "File 'emails.txt' not found. Please create it.", "red")
        except Exception as e:
            self._log_status("Main Process", f"An unexpected error occurred: {e}", "red")

if __name__ == "__main__":
    try:
        bot = Dawn()
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        console = Console()
        console.print(Panel("[bold]Exiting Dawn Login Tool...[/bold]", title="[bold red]INTERRUPTED[/bold red]", border_style="red"))
