from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from deep_translator import GoogleTranslator
import requests
import os
from collections import Counter
import ssl
import concurrent.futures
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# BrowserStack Credentials
username = "XXXXXXXXXXXXXXX"
access_key = "XXXXXXXXXXXXXXX"

# Disable SSL verification for secure requests
ssl._create_default_https_context = ssl._create_unverified_context

# Configure Selenium WebDriver options for headless browsing
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")

# Define browser configurations (mixing desktop and mobile)
browsers = [
    {'browser': 'Chrome', 'browser_version': 'latest', 'os': 'Windows', 'os_version': '10'},
    {'browser': 'Firefox', 'browser_version': 'latest', 'os': 'Windows', 'os_version': '10'},
    {'browser': 'Safari', 'browser_version': 'latest', 'os': 'macOS', 'os_version': 'Big Sur'},
    {'browser': 'iPhone', 'browser_version': 'latest', 'os': 'iOS', 'os_version': '14'},
    {'browser': 'Android', 'browser_version': 'latest', 'os': 'Android', 'os_version': '11'}
]

def handle_cookie_popup(driver):
    """Handles the cookie consent popup if it appears on the website."""
    try:
        # Check for the common 'Accept' button
        accept_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//*[text()='Accept'] | //button[contains(text(), 'Accept')]"))
        )
        accept_button.click()
        print("Cookie consent accepted.")
    except Exception as e:
        print("No cookie consent popup or failed to click. Error:", e)

def get_opinion_articles(driver):
    """
    Scrapes the first five opinion articles from El País.

    Args:
        driver: A Selenium WebDriver instance.

    Returns:
        List[dict]: A list of dictionaries containing title, content, and image path for each article.
    """
    try:
        driver.get("https://elpais.com/")
        handle_cookie_popup(driver)

        print("Navigating to the Opinion section...")
        for _ in range(3):
            try:
                opinion_section = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.LINK_TEXT, "Opinión"))
                )
                opinion_section.click()
                break
            except (StaleElementReferenceException, TimeoutException):
                print("Retrying to access the Opinion section...")
                time.sleep(2)
        else:
            print("Failed to access the Opinion section.")
            return []

        article_links = []
        articles = driver.find_elements(By.CSS_SELECTOR, "article a")
        seen_titles = set()  # To track seen titles and avoid duplicates

        for article in articles:
            try:
                link = article.get_attribute("href")
                if link and link not in article_links:
                    article_links.append(link)
                if len(article_links) >= 5:  # Stop collecting once we have 5 unique links
                    break
            except Exception as e:
                print("Error fetching article link:", e)

        article_data = []
        for link in article_links:
            try:
                # Fetch the article page content using requests
                response = requests.get(link)
                response.raise_for_status()

                # Parse the page with BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')

                # Try to find the title using multiple approaches
                title = None
                title_tag = soup.find('h1', class_='a_t')
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    print(f"Found title: {title}")
                else:
                    # If the title with class 'a_t' is not found in the first attempt, check all elements
                    print("Title with class 'a_t' not found, searching the entire document...")
                    all_h1_tags = soup.find_all('h1')
                    for h1 in all_h1_tags:
                        if 'a_t' in h1.get('class', []):
                            title = h1.get_text(strip=True)
                            print(f"Found title in another h1 with class 'a_t': {title}")
                            break

                if not title or title in seen_titles:  # Skip if no title or duplicate title
                    print(f"Skipping article with title: {title} (No title or duplicate)")
                    continue

                seen_titles.add(title)  # Add the valid title to the seen set

                # Find the content of the article
                paragraphs = soup.find_all('p')
                content = "\n".join(p.get_text() for p in paragraphs)

                # Handle the image extraction
                try:
                    image_element = soup.find('img') or soup.find('source', {'srcset': True})
                    image_url = image_element['src'] if image_element else None
                    if image_url:
                        response = requests.get(image_url, timeout=10)
                        response.raise_for_status()
                        os.makedirs("images", exist_ok=True)
                        image_path = os.path.join("images", f"{title[:10].strip().replace(' ', '_')}.jpg")
                        with open(image_path, "wb") as img_file:
                            img_file.write(response.content)
                    else:
                        image_path = None
                except Exception as e:
                    print("No image found or failed to download for article:", title, "Error:", e)
                    image_path = None

                article_data.append({
                    "title": title,
                    "content": content,
                    "image_path": image_path
                })

                if len(article_data) >= 5:  # Stop once we've collected 5 articles
                    break

            except Exception as e:
                print("Error processing article:", e)

        return article_data
    except Exception as e:
        print("Error during article scraping:", e)
        return []  

def translate_and_analyze(articles):
    """
    Translates article titles from Spanish to English and analyzes word frequency.

    Args:
        articles (List[dict]): List of articles with their metadata.
    """
    translated_headers = []

    # Translate titles to English
    print("Translating article titles...")
    for article in articles:
        try:
            translation = GoogleTranslator(source='es', target='en').translate(article["title"])
            translated_headers.append(translation)
        except Exception as e:
            print("Translation failed for title:", article["title"], "Error:", e)

    # Display translated titles
    print("\nTranslated Headers:")
    for i, header in enumerate(translated_headers, 1):
        print(f"{i}. {header}")

    # Analyze word frequency
    all_words = " ".join(translated_headers).lower().split()
    word_counts = Counter(all_words)
    repeated_words = {word: count for word, count in word_counts.items() if count >= 2}

    # Display repeated words
    print("\nRepeated Words:")
    if repeated_words:
        for word, count in repeated_words.items():
            print(f"{word}: {count}")
    else:
        print("No words repeated more than once.")

def run_browserstack_test(browser):
    """
    Run the test for a specific browser configuration on BrowserStack.
    """
    print(f"Running test on {browser['browser']} ({browser['os']} {browser['os_version']})")

    # Define the desired capabilities for each browser configuration
    desired_cap = {
    'bstack:options': {
        'os': browser['os'],
        'osVersion': browser['os_version'], 
        'browserName': browser['browser'], 
        'browserVersion': browser['browser_version'], 
        'local': 'false', 
        'seleniumVersion': '3.141.59'
    },
    'name': f"Test on {browser['browser']} ({browser['os']})"  # Test name for identification
}

    # If the browser is Chrome, pass the ChromeOptions for headless browsing
    if browser['browser'] == 'Chrome':
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.capabilities.update(desired_cap)  # Update options with desired capabilities
        driver = webdriver.Remote(
            command_executor=f'https://{username}:{access_key}@hub-cloud.browserstack.com/wd/hub',
            options=options  # Set up the ChromeOptions for ChromeDriver
        )
    else:
        # Use default desired capabilities for other browsers
        options = webdriver.ChromeOptions()  # Or another browser's options
        options.capabilities.update(desired_cap)  # Update options with desired capabilities
        driver = webdriver.Remote(
            command_executor=f'https://{username}:{access_key}@hub-cloud.browserstack.com/wd/hub',
            options=options  # Set up the desired capabilities for the WebDriver
        )

    # Get opinion articles on BrowserStack's remote browser
    articles = get_opinion_articles(driver)

    if articles:
        print("\nFetched Articles:")
        for i, article in enumerate(articles, 1):
            print(f"Article {i}:")
            print(f"  Title: {article['title']}")
            print(f"  Content snippet: {article['content'][:200]}...")
            print(f"  Image saved at: {article['image_path'] if article['image_path'] else 'No image available'}\n")

        print("\nAnalyzing Translations and Word Frequencies:\n")
        translate_and_analyze(articles)
    else:
        print("No articles were fetched.")

    driver.quit()
    
if __name__ == "__main__":
    print("Starting the BrowserStack tests in parallel...\n")

    # Use ThreadPoolExecutor to run tests in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Launch tests across multiple browsers and devices
        results = list(executor.map(run_browserstack_test, browsers))

    print("\nExecution complete.")
