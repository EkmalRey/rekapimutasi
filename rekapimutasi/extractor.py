from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError

from .errors import EmptyPDFError, PasswordProtectedError, WrongPasswordError


def extract_pdf_text(path, password=None):
    """Extract plain text from a PDF, decrypting AES-256 statements first.

    pypdf decrypts in place when ``is_encrypted`` and the owner/user password
    is empty (the BCA e-statement case); no temp file or separate decrypt step
    is needed. If ``password`` is provided, it attempts decryption with that password.
    """
    reader = PdfReader(path)
    if reader.is_encrypted:
        # First check if it decrypts with empty password (standard BCA owner-encrypted statement)
        res = reader.decrypt("")
        if res == 0:
            if password:
                res = reader.decrypt(password)
                if res == 0:
                    raise WrongPasswordError("Password yang dimasukkan salah.")
            else:
                raise PasswordProtectedError("File PDF dilindungi password.")

    pages = []
    try:
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    except FileNotDecryptedError:
        if password:
            raise WrongPasswordError("Password yang dimasukkan salah.")
        raise PasswordProtectedError("File PDF dilindungi password.")

    result = "\n".join(pages).strip()
    if not result:
        raise EmptyPDFError("empty pdf text")
    return result
