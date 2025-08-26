import io
import tarfile
import zipfile
from typing import List, Optional

try:
    import rarfile
    RARFILE_AVAILABLE = True
except ImportError:
    RARFILE_AVAILABLE = False

from .document import Document, ExtractorResult
from .extractor_base import BaseExtractor
from .helpers import detect_file_encodings


class ArchiveExtractor(BaseExtractor):
    """Extract text content from archive files (zip, tar, gz, rar)."""

    def __init__(self, file_bytes: bytes, file_name: str):
        """Initialize with file bytes and name."""
        self._file_bytes = file_bytes
        self._file_name = file_name

    def extract(self) -> ExtractorResult:
        """Extract documents from archive files.
            
        Returns:
            ExtractorResult object containing extracted content and documents
        """
        documents = []
        
        try:
            # Try to extract as ZIP file
            if self._is_zip_file(self._file_bytes):
                documents = self._extract_zip(self._file_bytes, self._file_name)
            # Try to extract as TAR file (including .tar.gz, .tar.bz2)
            elif self._is_tar_file(self._file_bytes):
                documents = self._extract_tar(self._file_bytes, self._file_name)
            # Try to extract as RAR file
            elif RARFILE_AVAILABLE and self._is_rar_file(self._file_bytes):
                documents = self._extract_rar(self._file_bytes, self._file_name)
            else:
                # If no format matches, return empty list
                documents = []
                
        except Exception as e:
            # If extraction fails, return an ExtractorResult with error info
            error_doc = Document(
                 page_content=f"Error extracting archive: {str(e)}",
                 metadata={"source": self._file_name, "error": True}
             )
            return ExtractorResult(
                md_content=f"Error extracting archive: {str(e)}",
                documents=[error_doc]
            )
            
        # Generate markdown summary
        if documents:
            file_list = [doc.metadata.get("file_path", "unknown") for doc in documents]
            md_content = f"# Archive Extraction Summary\n\nExtracted {len(documents)} files from archive:\n\n"
            for i, path in enumerate(file_list[:10], 1):
                md_content += f"{i}. {path}\n"
            if len(file_list) > 10:
                md_content += f"\n... and {len(file_list) - 10} more files"
        else:
            md_content = "# Archive Extraction Summary\n\nNo extractable text content found in the archive."
            
        return ExtractorResult(
            md_content=md_content,
            documents=documents
        )

    def _is_zip_file(self, file_content: bytes) -> bool:
        """Check if the file content is a ZIP file."""
        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
                # Try to read the file list to verify it's a valid ZIP
                zf.namelist()
                return True
        except (zipfile.BadZipFile, Exception):
            return False

    def _is_tar_file(self, file_content: bytes) -> bool:
        """Check if the file content is a TAR file."""
        try:
            with tarfile.open(fileobj=io.BytesIO(file_content)) as tf:
                # Try to read the file list to verify it's a valid TAR
                tf.getnames()
                return True
        except (tarfile.TarError, Exception):
            return False

    def _is_rar_file(self, file_content: bytes) -> bool:
        """Check if the file content is a RAR file."""
        if not RARFILE_AVAILABLE:
            return False
        try:
            with rarfile.RarFile(io.BytesIO(file_content)) as rf:
                # Try to read the file list to verify it's a valid RAR
                rf.namelist()
                return True
        except (rarfile.RarError, Exception):
            return False

    def _extract_zip(self, file_content: bytes, archive_name: Optional[str] = None) -> List[Document]:
        """Extract content from ZIP file."""
        documents = []
        
        with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
            for file_info in zf.infolist():
                # Skip directories
                if file_info.is_dir():
                    continue
                    
                try:
                    # Read file content
                    content_bytes = zf.read(file_info.filename)
                    
                    # Try to decode as text
                    text_content = self._decode_text_content(content_bytes)
                    
                    if text_content:
                        documents.append(Document(
                            page_content=text_content,
                            metadata={
                                "source": archive_name or "unknown",
                                "file_path": file_info.filename,
                                "file_size": file_info.file_size,
                                "archive_type": "zip"
                            }
                        ))
                except Exception as e:
                    # If individual file extraction fails, continue with others
                    continue
                    
        return documents

    def _extract_tar(self, file_content: bytes, archive_name: Optional[str] = None) -> List[Document]:
        """Extract content from TAR file."""
        documents = []
        
        with tarfile.open(fileobj=io.BytesIO(file_content)) as tf:
            for member in tf.getmembers():
                # Skip directories
                if member.isdir():
                    continue
                    
                try:
                    # Extract file content
                    file_obj = tf.extractfile(member)
                    if file_obj is None:
                        continue
                        
                    content_bytes = file_obj.read()
                    
                    # Try to decode as text
                    text_content = self._decode_text_content(content_bytes)
                    
                    if text_content:
                        documents.append(Document(
                            page_content=text_content,
                            metadata={
                                "source": archive_name or "unknown",
                                "file_path": member.name,
                                "file_size": member.size,
                                "archive_type": "tar"
                            }
                        ))
                except Exception as e:
                    # If individual file extraction fails, continue with others
                    continue
                    
        return documents

    def _extract_rar(self, file_content: bytes, archive_name: Optional[str] = None) -> List[Document]:
        """Extract content from RAR file."""
        if not RARFILE_AVAILABLE:
            return []
            
        documents = []
        
        with rarfile.RarFile(io.BytesIO(file_content)) as rf:
            for file_info in rf.infolist():
                # Skip directories
                if file_info.is_dir():
                    continue
                    
                try:
                    # Read file content
                    content_bytes = rf.read(file_info.filename)
                    
                    # Try to decode as text
                    text_content = self._decode_text_content(content_bytes)
                    
                    if text_content:
                        documents.append(Document(
                            page_content=text_content,
                            metadata={
                                "source": archive_name or "unknown",
                                "file_path": file_info.filename,
                                "file_size": file_info.file_size,
                                "archive_type": "rar"
                            }
                        ))
                except Exception as e:
                    # If individual file extraction fails, continue with others
                    continue
                    
        return documents

    def _decode_text_content(self, content_bytes: bytes) -> Optional[str]:
        """Try to decode bytes content as text."""
        if not content_bytes:
            return None
            
        # Skip binary files that are too large (> 10MB)
        if len(content_bytes) > 10 * 1024 * 1024:
            return None
            
        # Try to detect and decode text content
        try:
            encodings = detect_file_encodings(content_bytes)
            for encoding_info in encodings:
                try:
                    text_content = content_bytes.decode(encoding_info.encoding)
                    # Only return if it looks like text (contains printable characters)
                    if self._is_text_content(text_content):
                        return text_content
                except (UnicodeDecodeError, LookupError):
                    continue
        except Exception:
            pass
            
        return None

    def _is_text_content(self, content: str) -> bool:
        """Check if content appears to be text (not binary)."""
        if not content:
            return False
            
        # Check if content contains mostly printable characters
        printable_chars = sum(1 for c in content if c.isprintable() or c.isspace())
        total_chars = len(content)
        
        # Consider it text if at least 80% of characters are printable
        return (printable_chars / total_chars) >= 0.8 if total_chars > 0 else False