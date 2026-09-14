import msal

import config


def build_msal_app():
    return msal.PublicClientApplication(config.CLIENT_ID, authority=config.AUTHORITY)
