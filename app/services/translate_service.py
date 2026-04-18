from dotenv import load_dotenv
import os
from babel import Locale
from google.cloud import translate_v2 as translate

class Translate:
    def __init__(self):
        load_dotenv()
        self.client = translate.Client()

    def detect_language(self, text):
        """Detects the text's language."""
        # use the nmt model to translate for free 500K characters per month
        
        result = self.client.detect_language(text)
        return result['language']

    def translate(self, text, target_language):
        # use the nmt model to translate for free 500K characters per month
        try:
            result = self.client.translate(
                values=text,
                target_language=target_language,
                format_="text",  # 可選 text/html
                model="nmt"      # 強制使用 NMT 模型
            )

            return result["translatedText"]
        except Exception as e:
            print("Error during translation:", e)
            return None
        

    
    def get_language_name_in_chinese(self, language_code):
        try:
            locale = Locale.parse(language_code)
        except:
            return None

        # return the traditional chinese name of the language
        return locale.get_display_name('zh_Hant_TW')
