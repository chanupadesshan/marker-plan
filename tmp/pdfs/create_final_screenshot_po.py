from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from pypdf import PdfReader
import pypdfium2 as pdfium

root = Path(__file__).resolve().parents[2]
output = root / 'output/pdf/purchase-orders-all-screenshots.pdf'
output.parent.mkdir(parents=True, exist_ok=True)
orders = [
    ('361061', '24409', '1478', '1514', '8933', 504, [('-C48',84),('-C50',42),('-C52',84),('-C54',112),('-C56',70),('-C58',28),('-D92',14),('-D96',28),('-D100',14),('-D108',14),('-C152',14)]),
    ('355800', '16926', '1449', '1845', '8699', 1410, [('-C44',30),('-C46',90),('-C48',210),('-C50',240),('-C52',330),('-C54',270),('-C56',150),('-C58',30),('-C60',30),('-C62',30)]),
    ('362097', '', '7053', '1847', '9900', 800, [('-C32',40),('-C34',80),('-C36',112),('-C38',112),('-C40',96),('-C42',80),('-C44',48),('-C46',48),('-C48',32),('-C50',32),('-D18',16),('-D19',16),('-D20',16),('-D21',16),('-D22',16),('-D23',16),('-D24',16),('-D25',8)]),
    ('358449', '18693', '1530', '1310', '9900', 1671, [('-C44',54),('-C46',198),('-C48',360),('-C50',348),('-C52',378),('-C54',144),('-C56',90),('-C58',27),('-D100',18),('-D104',18),('-D108',9),('-C148',18),('-C154',9)]),
    ('359259', '18693', '1530', '1310', '9900', 954, [('-C44',36),('-C46',90),('-C48',216),('-C50',270),('-C52',126),('-C54',108),('-C56',36),('-D92',9),('-D100',9),('-D104',9),('-D108',9),('-D112',9),('-C148',9),('-C154',18)]),
]
c = canvas.Canvas(str(output), pagesize=letter)
c.setTitle('Purchase orders from all four supplied screenshots')
c.setSubject('Five PO contracts transcribed from all four supplied screenshots; BOM excluded.')
for page_number, (contract, techpack, model, quality, colour, total, sizes) in enumerate(orders, 1):
    assert sum(quantity for _, quantity in sizes) == total
    c.setFillColorRGB(.18,.18,.18)
    c.drawImage(str(root/'tmp/pdfs/logo.png'),51,732,width=98,height=31,mask='auto')
    c.setFont('Helvetica-Bold',10)
    c.drawRightString(558,749,'DRAFT')
    c.setFont('Helvetica-Bold',12)
    c.drawString(51,683,'Contract no')
    c.setFont('Helvetica',12)
    c.drawString(51,666,contract)
    for y, label, value in [(637,'teckpack:',techpack),(620,'Model ID:',model),(603,'QualityID:',quality),(586,'ColorID:',colour),(569,'Total quantity:',f'{total:,}')]:
        c.drawString(51,y,label)
        c.drawRightString(225,y,value)
    c.drawString(270,620,'Registered date:')
    c.drawString(270,591,'Date of shipping:')
    c.setLineWidth(.6)
    c.line(390,615,510,615)
    c.line(390,586,510,586)
    c.drawString(51,552,'Modified by user')
    c.setFont('Helvetica',11)
    c.drawString(158,552,'Gunilla Petersson')
    c.setFont('Helvetica',12)
    c.drawString(51,535,'signed_by:')
    c.line(130,527,225,527)
    c.setFont('Helvetica-Bold',12)
    for text,x,end in [('Size',51,118),('Quantity',128,181),('Price',189,243),('Amount',251,309),('Currency',315,369)]:
        c.drawString(x,501,text)
        c.line(x,491,end,491)
    c.setFont('Helvetica',12)
    for index,(size,quantity) in enumerate(sizes):
        y=481-15*index
        c.drawString(51,y,size)
        c.drawRightString(181,y,str(quantity))
    c.setFont('Helvetica',8)
    if not techpack:
        c.drawString(51,142,'Tech Pack number was not supplied for this contract.')
    c.drawString(51,40,'Missing fields are blank. Prices, currency, dates and signatures were not supplied.')
    c.drawRightString(558,20,str(page_number))
    c.showPage()
c.save()
reader=PdfReader(output)
assert len(reader.pages)==5
for page,(contract,techpack,model,quality,colour,total,sizes) in zip(reader.pages,orders):
    text=page.extract_text()
    assert all(value in text for value in [contract,techpack,model,quality,colour])
    assert f'{total:,}' in text and 'Gunilla Petersson' in text
    assert 'BOM' not in text and 'R1310' not in text
    for size,quantity in sizes:
        assert f'{size}\n{quantity}' in text
doc=pdfium.PdfDocument(str(output))
for index in range(len(doc)):
    doc[index].render(scale=1.1).to_pil().save(root/f'tmp/pdfs/all-po-{index+1}.png')
print(f'Created {output}; 5 pages; all size totals verified; total quantity {sum(order[5] for order in orders)}.')
