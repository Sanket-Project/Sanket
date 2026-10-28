"""Render the reviewed audit Markdown to a portable PDF with current evidence."""
from pathlib import Path
import re,html,json
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image,KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).parent
DEST=ROOT/'Sanket_Swecha_Readiness_Report.pdf'
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyAudit',fontName='Helvetica',fontSize=9.3,leading=13.5,spaceAfter=7,textColor=colors.HexColor('#24343e')))
styles.add(ParagraphStyle(name='SmallAudit',parent=styles['BodyAudit'],fontSize=8.2,leading=11,spaceAfter=5))
styles.add(ParagraphStyle(name='TitleAudit',fontName='Helvetica-Bold',fontSize=25,leading=30,spaceAfter=16,textColor=colors.HexColor('#083e43')))
styles.add(ParagraphStyle(name='H2Audit',fontName='Helvetica-Bold',fontSize=16,leading=21,spaceBefore=14,spaceAfter=10,textColor=colors.HexColor('#083e43'),keepWithNext=True))
styles.add(ParagraphStyle(name='H3Audit',fontName='Helvetica-Bold',fontSize=11.1,leading=15,spaceBefore=10,spaceAfter=7,textColor=colors.HexColor('#0b595e'),keepWithNext=True))
styles.add(ParagraphStyle(name='BulletAudit',parent=styles['BodyAudit'],leftIndent=12,firstLineIndent=-8,spaceAfter=6))
styles.add(ParagraphStyle(name='TableAudit',parent=styles['SmallAudit'],fontSize=8,leading=11,spaceAfter=0))

def clean(s):
    for old,new in [('₹','INR '),('→',' to '),('−','-'),('–','-'),('—',' - '),('’',"'"),('“','"'),('”','"'),('×','x'),('≤','<='),('≥','>='),('·',' / ')]:s=s.replace(old,new)
    return s
def rich(s):
    s=html.escape(clean(s))
    s=re.sub(r'\[([^]]+)\]\((https?://[^)]+)\)',r'<link href="\2" color="#08656c"><u>\1</u></link>',s)
    s=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',s)
    s=re.sub(r'`([^`]+)`',r'<font face="Courier" size="8.3">\1</font>',s)
    return s
def p(s,sty='BodyAudit'):return Paragraph(rich(s),styles[sty])

WIDTH=A4[0]-88
story=[p('INTERNAL REVIEW / 25 OCTOBER 2026 / ALL SAMPLE DATA SYNTHETIC','SmallAudit')]
lines=(ROOT/'REPORT.md').read_text(encoding='utf-8').splitlines();i=0
while i<len(lines):
    line=lines[i].strip()
    if not line:i+=1;continue
    if line.startswith('## 9.'):
        story.append(PageBreak());story.append(p('9. Screenshot evidence','H2Audit'))
        story.append(p('Captured in the repeated-upload stress workspace. Values are synthetic, including the deliberately inflated inputs. These screenshots prove the displayed states; they do not represent Swecha business performance.'))
        shots=[('01-dashboard.jpg','1. Dashboard renders; readiness overstates WhatsApp delivery.'),('02-forecast-claims.jpg','2. Forecast page: unsupported model/uplift copy and only four displayed SKUs.'),('03-inventory.jpg','3. Inventory: totals reconcile, but pending cover can look safe.'),('04-scenario.jpg','4. Scenario: demand preset finishes and changes the comparison.'),('05-accuracy.jpg','5. Accuracy: prerequisites shown, no invented measured score.'),('06-data-quality.jpg','6. Data quality correctly identifies 459 duplicate copies.'),('07-integrations.jpg','7. Integrations distinguishes live sources from future connectors.'),('08-whatsapp.jpg','8. WhatsApp correctly discloses that delivery is not configured.'),('09-trends.jpg','9. Zero signals incorrectly show 100% agreement.'),('10-sales-analytics.jpg','10. INR sales display is inflated 83x by currency conversion.'),('11-roi-labels.jpg','11. ROI claims observed savings; approval-linked values are estimates.')]
        for n,(file,caption) in enumerate(shots):
            if n and n%2==0:story.append(PageBreak())
            img=Image(str(ROOT/file));img.drawHeight=WIDTH*img.imageHeight/img.imageWidth;img.drawWidth=WIDTH
            story.append(KeepTogether([p(caption,'H3Audit'),img,Spacer(1,15)]))
        while i<len(lines) and not lines[i].startswith('## 10.'):i+=1
        continue
    if line.startswith('# '):story.append(p(line[2:],'TitleAudit'));i+=1;continue
    if line.startswith('## '):
        if line.startswith(('## 5.','## 7.')):story.append(PageBreak())
        story.append(p(line[3:],'H2Audit'));i+=1;continue
    if line.startswith('### '):story.append(p(line[4:],'H3Audit'));i+=1;continue
    if line.startswith('|'):
        rows=[]
        while i<len(lines) and lines[i].strip().startswith('|'):
            parts=[c.strip() for c in lines[i].strip().strip('|').split('|')]
            if not all(re.fullmatch('[: -]+',c or ' ') for c in parts):rows.append(parts)
            i+=1
        cols=len(rows[0]);widths={2:[WIDTH*.33,WIDTH*.67],3:[WIDTH*.28,WIDTH*.28,WIDTH*.44],5:[WIDTH*.15,WIDTH*.14,WIDTH*.15,WIDTH*.15,WIDTH*.41]}.get(cols,[WIDTH/cols]*cols)
        if cols==5:widths=[WIDTH*v for v in [.16,.15,.15,.16,.38]]
        table=Table([[p(c,'TableAudit') for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e3efee')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#8baead')),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#dce5e6'))]))
        story.extend([table,Spacer(1,9)])
        if rows[0][0]=='Clean sample result':
            img=Image(str(ROOT/'forecast-comparison.png'));img.drawHeight=WIDTH*img.imageHeight/img.imageWidth;img.drawWidth=WIDTH;story.extend([Spacer(1,8),img,Spacer(1,8)])
        continue
    if line.startswith('- '):story.append(p('- '+line[2:],'BulletAudit'));i+=1;continue
    if re.match(r'^\d+\. ',line):story.append(p(line,'BulletAudit'));i+=1;continue
    para=[line];i+=1
    while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','- ')):
        para.append(lines[i].strip());i+=1
    story.append(p(' '.join(para)))

def footer(canvas,doc):
    canvas.saveState();w,h=A4
    canvas.setStrokeColor(colors.HexColor('#d7e5e5'));canvas.line(44,35,w-44,35)
    canvas.setFont('Helvetica',7.3);canvas.setFillColor(colors.HexColor('#5c7078'))
    canvas.drawString(44,23,'SANKET / SWECHA READINESS / INTERNAL / SYNTHETIC TEST DATA')
    canvas.drawRightString(w-44,23,str(doc.page));canvas.restoreState()

doc=SimpleDocTemplate(str(DEST),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=40,bottomMargin=48,title='Sanket - Swecha Fashions Readiness Audit',author='Local product audit',pageCompression=1)
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(DEST)
