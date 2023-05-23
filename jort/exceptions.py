class JortException(Exception):
    pass


class JortCredentialException(JortException):
    """
    Exception for missing credentials.
    """
    pass