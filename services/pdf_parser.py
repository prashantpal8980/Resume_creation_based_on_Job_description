"""
PDF Parser Service
Extracts text content from PDF files using PyMuPDF (fitz).
Preserves structure (headings, bullets) for better AI processing.
"""

import fitz  # PyMuPDF
import os
import re


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from a PDF file, preserving structure.
    
    Args:
        pdf_path: Absolute path to the PDF file
        
    Returns:
        Extracted text as a string
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    doc = fitz.open(pdf_path)
    full_text = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Extract text blocks with position info for better structure preservation
        blocks = page.get_text("blocks")
        
        # Sort blocks by vertical position (top to bottom), then horizontal (left to right)
        blocks.sort(key=lambda b: (b[1], b[0]))
        
        for block in blocks:
            text = block[4].strip()
            if text:
                full_text.append(text)
    
    doc.close()
    
    # Join and clean up the text
    result = "\n".join(full_text)
    
    # Clean up excessive whitespace while preserving structure
    result = re.sub(r'\n{3,}', '\n\n', result)
    result = re.sub(r' {2,}', ' ', result)
    
    return result.strip()


def get_pdf_page_count(pdf_path: str) -> int:
    """Get the number of pages in a PDF file."""
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF bytes (for uploaded files).
    
    Args:
        pdf_bytes: Raw PDF file bytes
        
    Returns:
        Extracted text as a string
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (b[1], b[0]))
        
        for block in blocks:
            text = block[4].strip()
            if text:
                full_text.append(text)
    
    doc.close()
    
    result = "\n".join(full_text)
    result = re.sub(r'\n{3,}', '\n\n', result)
    result = re.sub(r' {2,}', ' ', result)
    
    return result.strip()
