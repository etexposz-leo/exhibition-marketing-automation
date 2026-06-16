"""Document parser for extracting text from various file formats."""

import io
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class DocumentParser:
    """Parse documents from PDF, DOCX, and TXT formats."""
    
    CHUNK_SIZE = 1000  # Characters per chunk
    CHUNK_OVERLAP = 200  # Overlap between chunks
    
    @staticmethod
    def parse_file(file_content: bytes, filename: str) -> str:
        """Parse file content and extract text."""
        ext = filename.lower().split('.')[-1]
        
        if ext == 'pdf':
            return DocumentParser._parse_pdf(file_content)
        elif ext in ['docx', 'doc']:
            return DocumentParser._parse_docx(file_content)
        elif ext == 'txt':
            return DocumentParser._parse_txt(file_content)
        else:
            raise ValueError(f"Unsupported file format: {ext}")
    
    @staticmethod
    def _parse_pdf(content: bytes) -> str:
        """Extract text from PDF."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            return '\n'.join(text_parts)
        except ImportError:
            logger.warning("pypdf not installed, using fallback")
            return DocumentParser._fallback_parse(content)
        except Exception as e:
            logger.error(f"PDF parsing error: {e}")
            raise ValueError(f"Failed to parse PDF: {str(e)}")
    
    @staticmethod
    def _parse_docx(content: bytes) -> str:
        """Extract text from DOCX."""
        try:
            from docx import Document
            doc = Document(io.BytesIO(content))
            paragraphs = []
            for para in doc.paragraphs:
                text = para.text.strip()
                if text:
                    paragraphs.append(text)
            return '\n'.join(paragraphs)
        except ImportError:
            logger.warning("python-docx not installed")
            raise ValueError("DOCX parsing requires python-docx")
        except Exception as e:
            logger.error(f"DOCX parsing error: {e}")
            raise ValueError(f"Failed to parse DOCX: {str(e)}")
    
    @staticmethod
    def _parse_txt(content: bytes) -> str:
        """Parse plain text file."""
        try:
            # Try UTF-8 first
            return content.decode('utf-8')
        except UnicodeDecodeError:
            # Fall back to latin-1
            return content.decode('latin-1')
    
    @staticmethod
    def _fallback_parse(content: bytes) -> str:
        """Fallback parser that tries to extract text from binary content."""
        try:
            text = content.decode('utf-8', errors='ignore')
            # Remove non-printable characters
            import re
            text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
            return text
        except Exception as e:
            logger.error(f"Fallback parsing error: {e}")
            raise ValueError("Failed to parse file content")
    
    @staticmethod
    def chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
        """Split text into overlapping chunks."""
        if chunk_size is None:
            chunk_size = DocumentParser.CHUNK_SIZE
        if overlap is None:
            overlap = DocumentParser.CHUNK_OVERLAP
        
        # Clean up text
        text = text.strip()
        if not text:
            return []
        
        # Split by sentences/paragraphs when possible
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = min(start + chunk_size, text_len)
            
            # Try to break at sentence or paragraph boundary
            if end < text_len:
                # Look for paragraph break
                for sep in ['\n\n', '\n', '. ', ' ']:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start + chunk_size // 2:
                        end = last_sep + len(sep)
                        break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            start = end - overlap if end < text_len else text_len
        
        return chunks
    
    @staticmethod
    def get_document_type(filename: str) -> Optional[str]:
        """Infer document type from filename."""
        filename_lower = filename.lower()
        
        type_keywords = {
            'exhibitor_manual': ['exhibitor', 'exhibitor manual', 'exhibitors'],
            'venue_rules': ['venue', 'venue rules', 'facility', 'facility guidelines'],
            'fire_safety': ['fire', 'fire safety', 'fire code', 'flammable'],
            'electrical': ['electrical', 'electric', 'power', 'voltage'],
            'hanging_signs': ['hanging', 'sign', 'overhead', ' rigging', 'signage'],
            'labor_rules': ['labor', 'union', 'work rules', 'contractor'],
            'booth_design': ['booth design', 'design guidelines', 'booth layout'],
        }
        
        for doc_type, keywords in type_keywords.items():
            for keyword in keywords:
                if keyword in filename_lower:
                    return doc_type
        
        return 'other'
    
    @staticmethod
    def extract_metadata(text: str) -> dict:
        """Extract basic metadata from document text."""
        metadata = {
            'char_count': len(text),
            'word_count': len(text.split()),
            'line_count': text.count('\n') + 1,
        }
        
        # Try to extract event/venue info
        import re
        event_pattern = r'(CES|NAB|InfoComm|Pack Expo|SXSW|Web Summit|Consumer Electronics Show|National Association of Broadcasters)'
        venue_pattern = r'(Las Vegas|Las Vegas Convention Center|LVCC|McCormick Place|Javits|O2|Expo Hall)'
        year_pattern = r'(20\d{2})'
        
        event_match = re.search(event_pattern, text, re.IGNORECASE)
        venue_match = re.search(venue_pattern, text, re.IGNORECASE)
        year_match = re.search(year_pattern, text)
        
        if event_match:
            metadata['event_name'] = event_match.group(1)
        if venue_match:
            metadata['venue_name'] = venue_match.group(1)
        if year_match:
            metadata['year'] = int(year_match.group(1))
        
        return metadata


# Demo content for exhibition booth rules
DEMO_DOCUMENTS = {
    "ces_booth_rules": """
    CES EXHIBITOR MANUAL - BOOTH DESIGN GUIDELINES
    
    Maximum Booth Height: 16 feet (4.88 meters) for inline booths
    Corner booths may have up to 12 feet height on the two open sides
    
    HANGING SIGNS AND GRAPHICS:
    - Hanging signs are allowed ONLY for peninsula, island, and perimeter booths
    - Maximum hanging sign height: 20 feet from floor to top of sign
    - Signs must be setback 1 foot from adjacent booth inline walls
    - All hanging signs require advance approval from show management
    - Rigging point locations must be confirmed with venue
    
    ELECTRICAL REQUIREMENTS:
    - All electrical work must be performed by venue-authorized contractors
    - Minimum 500 watts per 100 square feet of booth space
    - GFCI protection required for all wet locations
    - 208V 3-phase power available for large displays
    - Pre-order electrical services 30 days before move-in
    
    FIRE SAFETY:
    - All materials used in booth must be flame retardant
    - Required: Certificate of Flame Resistance for all fabrics
    - No open flames or pyrotechnics without written approval
    - Fire extinguishers required for booths over 300 sq ft
    - Exit pathways must remain clear at all times
    
    LABOR RULES:
    - Union labor required for all rigging, electrical, and plumbing
    - Material handling through official drayage company only
    - Forklift operations require certified operators
    - Crew chief required for booths over 20x20
    - Overtime rates apply before 8 AM and after 6 PM
    
    BOOTH CONSTRUCTION:
    - Maximum 2-story booths require structural engineering approval
    - Solid walls limited to 50% of booth perimeter
    - Transparent barriers encouraged for visibility
    - Canopy/deck installations require permits
    """,
    "fire_safety_general": """
    EXHIBITION FIRE SAFETY REGULATIONS
    
    FLAME RETARDANT REQUIREMENTS:
    - All decorative materials must be flame retardant
    - Approved fabrics have a flame spread rating of 25 or less
    - Foam materials generally NOT permitted
    - Certification documentation must be available on-site
    
    FIRE SUPPRESSION:
    - Sprinkler heads must remain unobstructed (18" clearance)
    - Booths cannot exceed 300 sq ft without fire extinguisher
    - ABC-rated fire extinguishers required per 600 sq ft
    - Automatic fire suppression for cooking demonstrations
    
    COMBUSTIBLE MATERIALS:
    - Cardboard boxes must be removed from booth area
    - Packing materials limited to essential supplies
    - Flammable liquids prohibited in booths
    - Compressed gas cylinders must be secured and capped
    
    EMERGENCY ACCESS:
    - Main aisle width minimum: 10 feet
    - Cross aisles required every 100 feet in large halls
    - Emergency exits clearly marked and unobstructed
    - Booth personnel must know evacuation procedures
    """,
    "electrical_requirements": """
    EXHIBITION ELECTRICAL STANDARDS
    
    POWER DISTRIBUTION:
    - Standard service: 120V single phase
    - Premium service: 208V or 480V three phase
    - Minimum order: 500W per 100 sq ft booth
    - Island booths require underground power
    
    ELECTRICAL SAFETY:
    - GFCI protection required for all circuits
    - Liquid-tight connectors for wet areas
    - No exposed wiring permitted
    - All circuits must be properly grounded
    - Overcurrent protection within 6 feet of connection
    
    LIGHTING:
    - Low-voltage LED lighting preferred
    - Track lighting must be permanently mounted
    - Glowing tubes require plastic sleeves
    - Spotlights limited to product illumination
    
    SPECIAL REQUIREMENTS:
    - Motor loads require separate circuits
    - Plasma/LCD screens need dedicated circuits
    - Cooking equipment requires hood suppression
    - Generator fuel storage regulated by fire code
    """,
    "hanging_signs": """
    HANGING SIGN AND RIGGING GUIDELINES
    
    ELIGIBILITY:
    - Peninsula, island, and perimeter booths ONLY
    - Inline and corner booths: hanging signs NOT permitted
    - Check show map for booth type designation
    
    DIMENSIONS:
    - Maximum height: 20 feet from floor to top
    - Minimum clearance from floor: 7 feet 6 inches
    - Maximum width: booth width minus 1 foot each side
    - Structural support points must be identified
    
    APPROVAL PROCESS:
    - Submit hanging sign request 30 days before show
    - Include: dimensions, weight, rigging plan, engineering cert
    - Venue must confirm rigging point availability
    - Additional fees apply for hanging signs
    
    RIGGING REQUIREMENTS:
    - All rigging by venue-certified riggers
    - Minimum 2:1 safety factor required
    - Chain hoists preferred over wire rope
    - Motorized lifts for signs over 100 lbs
    - Rigging points must support 1000 lbs minimum
    """,
}


def get_demo_document_content(doc_type: str = None) -> str:
    """Get demo document content for testing."""
    if doc_type == "ces_rules" or doc_type == "exhibitor_manual":
        return DEMO_DOCUMENTS["ces_booth_rules"]
    elif doc_type == "fire_safety":
        return DEMO_DOCUMENTS["fire_safety_general"]
    elif doc_type == "electrical":
        return DEMO_DOCUMENTS["electrical_requirements"]
    elif doc_type == "hanging_signs":
        return DEMO_DOCUMENTS["hanging_signs"]
    else:
        # Return combined demo content
        return "\n\n---\n\n".join(DEMO_DOCUMENTS.values())
