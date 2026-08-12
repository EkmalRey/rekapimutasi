from pypdf import PdfReader

from .errors import EmptyPDFError


def extract_pdf_text(path):
    """Extract plain text from a PDF, decrypting AES-256 statements first.

    pypdf decrypts in place when ``is_encrypted`` and the owner/user password
    is empty (the BCA e-statement case); no temp file or separate decrypt step
    is needed.
    """
    reader = PdfReader(path)
    if reader.is_encrypted:
        reader.decrypt("")

    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)

    result = "\n".join(pages).strip()
    if not result:
        raise EmptyPDFError("empty pdf text")
    return result
