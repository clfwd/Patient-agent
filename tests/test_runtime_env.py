import os
import tempfile
import unittest
from pathlib import Path

from app.runtime_env import load_dotenv_file


class RuntimeEnvTest(unittest.TestCase):
    def test_load_dotenv_file_populates_missing_env_vars(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "AGENT_LLM_PROVIDER=openai",
                        "OPENAI_MODEL=gpt-4o",
                        'QWEN_OMNI_TTS_VOICE="Cherry"',
                    ]
                ),
                encoding="utf-8",
            )

            original_values = {key: os.environ.get(key) for key in ["AGENT_LLM_PROVIDER", "OPENAI_MODEL", "QWEN_OMNI_TTS_VOICE"]}
            try:
                for key in original_values:
                    os.environ.pop(key, None)

                result = load_dotenv_file(env_path)

                self.assertTrue(result["loaded"])
                self.assertEqual(result["count"], 3)
                self.assertEqual(os.environ["AGENT_LLM_PROVIDER"], "openai")
                self.assertEqual(os.environ["OPENAI_MODEL"], "gpt-4o")
                self.assertEqual(os.environ["QWEN_OMNI_TTS_VOICE"], "Cherry")
            finally:
                for key, value in original_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_load_dotenv_file_does_not_override_existing_env_vars_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("OPENAI_MODEL=gpt-4o\n", encoding="utf-8")

            original_value = os.environ.get("OPENAI_MODEL")
            try:
                os.environ["OPENAI_MODEL"] = "existing-model"

                result = load_dotenv_file(env_path)

                self.assertTrue(result["loaded"])
                self.assertEqual(result["count"], 0)
                self.assertEqual(os.environ["OPENAI_MODEL"], "existing-model")
            finally:
                if original_value is None:
                    os.environ.pop("OPENAI_MODEL", None)
                else:
                    os.environ["OPENAI_MODEL"] = original_value
