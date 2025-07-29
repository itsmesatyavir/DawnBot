import json
from colorama import init, Fore, Style

init(autoreset=True)

def create_accounts_json():
    print(Fore.CYAN + Style.BRIGHT + "\n[SETUP] Create accounts.json\n")
    
    try:
        count = int(input(Fore.YELLOW + Style.BRIGHT + ">> How many accounts do you want to save? ").strip())
        if count <= 0:
            print(Fore.RED + Style.BRIGHT + "[ERROR] Enter a number greater than 0.")
            return
    except ValueError:
        print(Fore.RED + Style.BRIGHT + "[ERROR] Invalid number entered.")
        return

    accounts = []

    for i in range(count):
        print(Fore.GREEN + Style.BRIGHT + f"\n[ACCOUNT {i+1}]")
        name = input("  Name  : ").strip()
        email = input("  Email : ").strip()
        token = input("  Token : ").strip()

        if not all([name, email, token]):
            print(Fore.RED + Style.BRIGHT + "[ERROR] All fields are required. Skipping this entry.")
            continue

        accounts.append({
            "name": name,
            "email": email,
            "token": token
        })

    if accounts:
        with open("accounts.json", "w") as f:
            json.dump(accounts, f, indent=2)
        print(Fore.GREEN + Style.BRIGHT + f"\n[SAVED] {len(accounts)} account(s) saved to accounts.json\n")
    else:
        print(Fore.RED + Style.BRIGHT + "[WARNING] No valid accounts to save.\n")

if __name__ == "__main__":
    create_accounts_json()
