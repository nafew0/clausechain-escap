import os


PROVIDER_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def get_ai_api_key_env_var(provider):
    return PROVIDER_ENV_VARS.get((provider or "").strip().lower(), "")


def get_ai_api_key(settings_obj, provider):
    env_var_name = get_ai_api_key_env_var(provider)
    return (os.environ.get(env_var_name, "") or "").strip()


def get_ai_api_key_meta(settings_obj, provider):
    env_var_name = get_ai_api_key_env_var(provider)
    env_value = (os.environ.get(env_var_name, "") or "").strip()
    if env_value:
        return {
            "configured": True,
            "value": env_value,
            "source": "environment",
        }

    return {
        "configured": False,
        "value": "",
        "source": "environment",
    }
