from pathlib import Path
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader
import pypdfium2 as pdfium

root = Path(__file__).resolve().parents[2]
sources = Path('C:/Users/chanupa.d/Documents/marker plans')
files = [sources/'marker plan 01/BOM.png', sources/'maker plan 02/BOM.png',
         sources/'marker plan 03/BOM.png', sources/'marker plan 04/PO and BOM.png']
output = root/'output/pdf/boms-all-four-screenshots.pdf'
output.parent.mkdir(parents=True, exist_ok=True)
width, height = landscape(A4)
c = canvas.Canvas(str(output), pagesize=(width, height))
c.setTitle('BOM collection - all four supplied screenshots')
c.setSubject('Four original BOM tables, one per page. Purchase orders excluded.')
for index, source in enumerate(files, 1):
    image = Image.open(source).convert('RGB')
    if index == 4:
        # Only the BOM region of the combined screenshot; both POs are excluded.
        assert image.size == (970, 376), image.size
        image = image.crop((369, 22, 888, 211))
    c.setFillColorRGB(.16,.16,.19)
    c.setFont('Helvetica-Bold',18)
    c.drawString(36,height-42,f'BOM {index:02d}')
    c.setFont('Helvetica',9)
    c.setFillColorRGB(.47,.47,.51)
    c.drawRightString(width-36,height-40,f'Marker plan {index:02d}')
    c.setStrokeColorRGB(.85,.85,.88)
    c.setLineWidth(.5)
    c.line(36,height-55,width-36,height-55)
    available_width, available_height = width-72, height-112
    scale = min(available_width/image.width, available_height/image.height)
    image_width, image_height = image.width*scale, image.height*scale
    c.drawImage(ImageReader(image),(width-image_width)/2,height-78-image_height,
                width=image_width,height=image_height)
    c.setFont('Helvetica',8)
    c.drawRightString(width-36,24,f'{index} / 4')
    c.showPage()
c.save()
reader=PdfReader(output)
assert len(reader.pages)==4
for i,page in enumerate(reader.pages,1):
    assert f'BOM {i:02d}' in page.extract_text()
    assert len(page.images)==1
doc=pdfium.PdfDocument(str(output))
for i in range(len(doc)):
    doc[i].render(scale=1.2).to_pil().save(root/f'tmp/pdfs/bom-preview-{i+1}.png')
print(f'Created {output}; four pages, four BOM tables; no purchase-order content.')
