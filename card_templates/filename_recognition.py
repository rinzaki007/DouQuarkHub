"""Global filename recognition card."""
from moviesync.cards import Card, CardManifest

class FilenameRecognitionCard(Card):
    manifest = CardManifest(id="filename_recognition", name="文件名识别", type="filename_processor", description="全局文件名识别规则。", capabilities=("filename.parse",))
    def validate_config(self, config):
        return super().validate_config(config)

def create_card(context):
    return FilenameRecognitionCard()
