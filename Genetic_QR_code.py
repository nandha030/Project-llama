import os
import sys
import qrcode
import logging
import hashlib
import mimetypes
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from pathlib import Path
import shutil
from PIL import Image
import numpy as np
from cryptography.fernet import Fernet
import base64
import zlib
import json

class FileProcessor:
    """Handles file processing and validation"""
    
    ALLOWED_EXTENSIONS = {
        'text': {'.txt', '.doc', '.docx', '.pdf'},
        'audio': {'.mp3', '.wav', '.ogg', '.m4a'},
        'video': {'.mp4', '.avi', '.mov', '.mkv'},
        'image': {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}
    }
    
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB limit
    
    def __init__(self):
        self.logger = self._setup_logger()
        
    def _setup_logger(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = logging.getLogger('FileProcessor')
        logger.setLevel(logging.INFO)
        
        # Create handlers
        c_handler = logging.StreamHandler()
        f_handler = logging.FileHandler('file_processing.log')
        
        # Create formatters
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        c_handler.setFormatter(formatter)
        f_handler.setFormatter(formatter)
        
        # Add handlers
        logger.addHandler(c_handler)
        logger.addHandler(f_handler)
        
        return logger
    
    def validate_file(self, file_path: str) -> Tuple[bool, str]:
        """Validate file type and size"""
        try:
            if not os.path.exists(file_path):
                return False, "File does not exist"
                
            file_size = os.path.getsize(file_path)
            if file_size > self.MAX_FILE_SIZE:
                return False, f"File size exceeds limit of {self.MAX_FILE_SIZE/1024/1024}MB"
                
            file_ext = os.path.splitext(file_path)[1].lower()
            valid_ext = False
            
            for extensions in self.ALLOWED_EXTENSIONS.values():
                if file_ext in extensions:
                    valid_ext = True
                    break
                    
            if not valid_ext:
                return False, "File type not supported"
                
            return True, "File validation successful"
            
        except Exception as e:
            self.logger.error(f"File validation error: {str(e)}")
            return False, f"Validation error: {str(e)}"

class GeneticQRGenerator:
    """Handles Stealth Genetic Pattern QR code generation"""
    
    def __init__(self):
        self.encryption_key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.encryption_key)
        self.logger = logging.getLogger('GeneticQRGenerator')
        
    def compress_data(self, data: bytes) -> bytes:
        """Compress data using zlib"""
        try:
            return zlib.compress(data, level=9)
        except Exception as e:
            self.logger.error(f"Compression error: {str(e)}")
            raise
            
    def encrypt_data(self, data: bytes) -> bytes:
        """Encrypt data using Fernet"""
        try:
            return self.cipher_suite.encrypt(data)
        except Exception as e:
            self.logger.error(f"Encryption error: {str(e)}")
            raise
            
    def generate_qr(self, data: bytes, metadata: Dict) -> Image.Image:
        """Generate QR code with genetic patterns"""
        try:
            # Prepare data package
            package = {
                'data': base64.b64encode(data).decode('utf-8'),
                'metadata': metadata,
                'timestamp': datetime.now().isoformat()
            }
            
            # Convert to JSON and compress
            json_data = json.dumps(package)
            compressed_data = self.compress_data(json_data.encode())
            
            # Encrypt the compressed data
            encrypted_data = self.encrypt_data(compressed_data)
            
            # Generate QR code
            qr = qrcode.QRCode(
                version=40,  # Maximum version for highest storage
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4
            )
            
            qr.add_data(encrypted_data)
            qr.make(fit=True)
            
            return qr.make_image(fill_color="black", back_color="white")
            
        except Exception as e:
            self.logger.error(f"QR generation error: {str(e)}")
            raise

class FileToQRConverter:
    """Main class for converting files to Stealth Genetic Pattern QR codes"""
    
    def __init__(self):
        self.file_processor = FileProcessor()
        self.qr_generator = GeneticQRGenerator()
        self.logger = logging.getLogger('FileToQRConverter')
        
    def setup_output_directory(self) -> str:
        """Setup output directory for QR codes"""
        try:
            output_dir = os.path.join(os.getcwd(), 'QR_Codes')
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            return output_dir
        except Exception as e:
            self.logger.error(f"Directory setup error: {str(e)}")
            raise
            
    def generate_qr_filename(self, original_filename: str) -> str:
        """Generate unique filename for QR code"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name = os.path.splitext(os.path.basename(original_filename))[0]
        return f"QR_{base_name}_{timestamp}.png"
        
    def convert_file_to_qr(self, file_path: str) -> Optional[str]:
        """Convert file to QR code and save it"""
        try:
            # Validate file
            is_valid, message = self.file_processor.validate_file(file_path)
            if not is_valid:
                self.logger.error(f"File validation failed: {message}")
                return None
                
            # Read file data
            with open(file_path, 'rb') as f:
                file_data = f.read()
                
            # Prepare metadata
            metadata = {
                'filename': os.path.basename(file_path),
                'filesize': os.path.getsize(file_path),
                'mimetype': mimetypes.guess_type(file_path)[0],
                'checksum': hashlib.sha256(file_data).hexdigest()
            }
            
            # Generate QR code
            qr_image = self.qr_generator.generate_qr(file_data, metadata)
            
            # Save QR code
            output_dir = self.setup_output_directory()
            qr_filename = self.generate_qr_filename(file_path)
            output_path = os.path.join(output_dir, qr_filename)
            
            qr_image.save(output_path)
            self.logger.info(f"QR code generated successfully: {output_path}")
            
            return output_path
            
        except Exception as e:
            self.logger.error(f"Conversion error: {str(e)}")
            return None

def main():
    """Main function to run the converter"""
    converter = FileToQRConverter()
    
    if len(sys.argv) < 2:
        print("Usage: python script.py <file_path>")
        return
        
    file_path = sys.argv[1]
    output_path = converter.convert_file_to_qr(file_path)
    
    if output_path:
        print(f"QR code generated successfully: {output_path}")
    else:
        print("Failed to generate QR code. Check logs for details.")

if __name__ == "__main__":
    # Setup basic logging configuration
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        main()
    except Exception as e:
        logging.error(f"Application error: {str(e)}")
        sys.exit(1)