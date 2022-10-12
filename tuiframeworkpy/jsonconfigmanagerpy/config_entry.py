from typing import Any


class ConfigEntry:
    __slots__ = ['name', 'friendly_name', 'default_value', 'prompt_text', 'prompt', 'is_path', 'is_bool_prompt', 'censor']

    def __init__(self, name: str, friendly_name: str, default_value: Any, prompt_text: str, prompt: bool = True, is_path: bool = False, is_bool_prompt=False, censor=False):
        self.name = name
        self.friendly_name = friendly_name
        self.default_value = default_value
        self.prompt_text = prompt_text
        self.prompt = prompt
        self.is_path = is_path
        self.is_bool_prompt = is_bool_prompt
        self.censor = censor


    def __getitem__(self, i) -> Any:
        return getattr(self, i, None)
