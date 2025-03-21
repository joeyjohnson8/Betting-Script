import discord
import numpy as np
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import asyncio

import os

driver_path = "/Users/joeyjohnson/Downloads/done/chromedriver"


# Discord bot setup
TOKEN = "" # Replace with your bot token
CHANNEL_ID = 0  # Replace with the ID of the Discord channel to send messages to

intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"We have logged in as {client.user}")
    await scrape_and_send_results()

# Function to calculate implied probabilities using devigging methods
def multiplicative_method(odds):
    pi = 1 / odds
    normalization = sum(pi)
    return pi / normalization

def additive_method(odds):
    pi = 1 / odds
    return pi + 1 / len(odds) * (1 - sum(pi))

def power_method(odds, tol=1e-6, max_iter=1000):
    p = 1 / odds
    left, right = 0.1, 10.0
    for _ in range(max_iter):
        k = (left + right) / 2
        p_adj = p ** k
        total = sum(p_adj)
        if abs(total - 1) < tol:
            return p_adj / total
        elif total < 1:
            right = k
        else:
            left = k
    p_adj = p ** ((left + right) / 2)
    return p_adj / sum(p_adj)

def worst_case_method(odds):
    multiplicative = multiplicative_method(odds)
    additive = additive_method(odds)
    power = power_method(odds)
    return np.minimum(np.minimum(multiplicative, additive), power)

def american_to_decimal(american_odds):
    if american_odds > 0:
        return (american_odds / 100) + 1
    else:
        return (100 / abs(american_odds)) + 1

def calculate_ev(probability, decimal_odds):
    payout = decimal_odds - 1
    return (probability * payout) - (1 - probability)

async def scrape_and_send_results(driver, tabs):
    """
    Rereads the tables from already open tabs and processes data.
    """
    message = ""

    for i, tab in enumerate(tabs):
        # Switch to the corresponding tab
        driver.switch_to.window(tab)

        # Wait for the table to load and locate it
        try:
            wait = WebDriverWait(driver, 10)
            table = wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
            rows = table.find_elements(By.TAG_NAME, "tr")[1:]  # Skip the header row

            # Process rows
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                game_info = [cell.text for cell in cells]

                # Check if the row has sufficient columns
                if len(game_info) > max(71, 12):
                    if game_info[71].strip() != "-\n-" and game_info[12].strip() != "-\n-":
                        print(game_info[0])
                        ubet_away_odds = int(game_info[71].split("\n")[0].replace("+", ""))
                        ubet_home_odds = int(game_info[71].split("\n")[1].replace("+", ""))
                        pinny_away_odds = int(game_info[12].split("\n")[0].replace("+", ""))
                        pinny_home_odds = int(game_info[12].split("\n")[2].replace("+", ""))
                        pinny_away_limit = game_info[13].split("\n")[0]  # Assuming limits are in adjacent columns
                        pinny_home_limit = game_info[13].split("\n")[1]

                        pinny_decimal_odds = np.array([
                            american_to_decimal(pinny_away_odds),
                            american_to_decimal(pinny_home_odds)
                        ])

                        fair_probs = worst_case_method(pinny_decimal_odds)

                        ubet_decimal_odds = np.array([
                            american_to_decimal(ubet_away_odds),
                            american_to_decimal(ubet_home_odds)
                        ])

                        ubet_away_ev = calculate_ev(fair_probs[0], ubet_decimal_odds[0]) * 100
                        ubet_home_ev = calculate_ev(fair_probs[1], ubet_decimal_odds[1]) * 100

                        if ubet_away_ev > 0 or ubet_home_ev > 0:
                            if i == 0:
                                if ubet_away_ev > 0:
                                    message+= f"{game_info[0][0].split()[0]} Moneyline"
                                elif ubet_home_ev > 0:
                                    message+= f"{game_info[0][0].split()[1]} Moneyline"
                            elif i == 1:
                                if ubet_away_ev > 0:
                                    message+= f"{game_info[0][0].split()[0]} Spread"
                                elif ubet_home_ev > 0:
                                    message+= f"{game_info[0][0].split()[1]} Spread"
                            else:
                                if ubet_away_ev > 0:
                                    message+= f"{game_info[0][0].split()[0]} Over"
                                elif ubet_home_ev > 0:
                                    message+= f"{game_info[0][0].split()[1]} Under" 
                            message += f"Tab {i+1}:\n"
                            message += f"Pinny Away Odds: {pinny_away_odds}, Pinny Home Odds: {pinny_home_odds}\n"
                            message += f"Ubet Away Odds: {ubet_away_odds}, EV%: {ubet_away_ev:.2f}%\n"
                            message += f"Ubet Home Odds: {ubet_home_odds}, EV%: {ubet_home_ev:.2f}%\n"
                            message += "-" * 50 + "\n"

        except Exception as e:
            print(f"Error processing tab {i+1}: {e}")

    # Send message to Discord
    channel = client.get_channel(CHANNEL_ID)
    if message:
        await channel.send(f"**Value Bets Found:**\n{message}")
    else:
        await channel.send("No positive EV bets found.")


async def periodic_scraping():
    """
    Opens tabs for each URL and periodically processes the tables without reloading.
    """
    # Selenium setup
    service = Service(executable_path="chromedriver.exe")
    print(service)
    driver = webdriver.Chrome(service=service)

    # List of pages to scrape
    urls = [
        "https://picktheodds.app/en/odds-screen?league=NBA&group=MONEY_LINE&time=MONEY_LINE",
        "https://picktheodds.app/en/odds-screen?league=NBA&group=SPREAD&time=SPREAD&betGroup=SPREAD",
        "https://picktheodds.app/en/odds-screen?league=NBA&group=TOTAL_GAME_POINTS&time=TOTAL_GAME_POINTS&betGroup=TOTALS"
    ]

    # Open all tabs
    tabs = []
    try:
        for i, url in enumerate(urls):
            if i > 0:
                # Open a new tab
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[i])  # Switch to the new tab
            driver.get(url)
            tabs.append(driver.current_window_handle)  # Store the tab handle

        # Periodically process the tables
        while True:
            await scrape_and_send_results(driver, tabs)
            await asyncio.sleep(120)  # Wait for 2 minutes (120 seconds)

    finally:
        driver.quit()


@client.event
async def on_ready():
    print(f"We have logged in as {client.user}")
    await periodic_scraping()


client.run(TOKEN)

