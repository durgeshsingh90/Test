from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom
from bs4 import BeautifulSoup

# Sample HTML snippet as a string
html_snippet = """
<tr>
  <td class="cell1norm">&nbsp;DE055</td>
  <td class="cell2norm">ICC data</td>
  <td class="cell3">B...256</td>
  <td class="cell4">31 30 32</td>
  <td class="cell5">9F 02 06 00 00 00 00 92 00 82 02 10 00 9F 36 02 00 02 9F 26 08 C7 DF 35 B3 8E 4D E3 0B 9F 27 01 80 84 07 A0 00 00 01 52 30 10 9F 1E 08 31 39 32 36 35 30 36 31 9F 10 0A 01 15 00 00 00 00 00 00 00 00 9F 09 02 00 01 9F 33 03 60 60 08 9F 1A 02 04 70 9F 35 01 22 95 05 80 80 04 80 00 9A 03 22 08 10 9C 01 00 5F 2A 02 09 78 9F 37 04 B8 24 62 7D</td>
  <td class="cell6">226</td>
  <td class="cell7">9F 02 06 00 00 00 00 92 00 82 02 10 00 9F 36 02 00 02 9F 26 08 C7 DF 35 B3 8E 4D E3 0B 9F 27 01 80 84 07 A0 00 00 01 52 30 10 9F 1E 08 31 39 32 36 35 30 36 31 9F 10 0A 01 15 00 00 00 00 00 00 00 00 9F 09 02 00 01 9F 33 03 60 60 08 9F 1A 02 04 70 9F 35 01 22 95 05 80 80 04 80 00 9A 03 22 08 10 9C 01 00 5F 2A 02 09 78 9F 37 04 B8 24 62 7D</td>
  <td class="cell8norm">&nbsp;</td>
</tr>
<tr>
  <td class="cell1norm">&nbsp;&nbsp;EMVTAG-9F02</td>
  <td class="cell2norm">Amount (Authorized) Numeric</td>
  <td class="cell3">TLV</td>
  <td class="cell4">&nbsp;</td>
  <td class="cell5">9F02-06-000000000300</td>
  <td class="cell6">&nbsp;</td>
  <td class="cell7">9F02-06-000000000300</td>
  <td class="cell8norm">Value of 300</td>
</tr>
<tr>
  <td class="cell1norm">&nbsp;&nbsp;EMVTAG-82</td>
  <td class="cell2norm">Application Interchange Profile</td>
  <td class="cell3">TLV</td>
  <td class="cell4">&nbsp;</td>
  <td class="cell5">82-02-1100</td>
  <td class="cell6">&nbsp;</td>
  <td class="cell7">82-02-1100</td>
  <td class="cell8norm">&nbsp;</td>
</tr>
<tr>
  <td class="cell1norm">&nbsp;&nbsp;&nbsp;Byte 1#5, oooX oooo</td>
  <td class="cell2norm"> </td>
  <td class="cell3"> </td>
  <td class="cell4"> </td>
  <td class="cell5">...1 ....</td>
  <td class="cell6"> </td>
  <td class="cell7">...1 ....</td>
  <td class="cell8norm">Cardholder verification is supported</td>
</tr>
<tr>
  <td class="cell1norm">&nbsp;&nbsp;&nbsp; </td>
  <td class="cell2norm"> </td>
  <td class="cell3"> </td>
  <td class="cell4"> </td>
  <td class="cell5"> </td>
  <td class="cell6"> </td>
  <td class="cell7"> </td>
  <td class="cell8norm">KDI (Key Derivation Index): 0x01</td>
</tr>
"""

# Function to create XML element with text content
def create_element(parent, tag, text=None):
    element = SubElement(parent, tag)
    if text:
        element.text = text
    return element

# Function to prettify the XML output
def prettify_xml(elem):
    rough_string = tostring(elem, 'utf-8')
    reparsed = xml.dom.minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")

# Parse the HTML with BeautifulSoup
soup = BeautifulSoup(html_snippet, "html.parser")

# Create the root element for the XML
root = Element("Field", {"ID": "NET.1100.DE.055"})

# Parse the first row
first_row = soup.find_all('tr')[0]
create_element(root, "FriendlyName", first_row.find_all('td')[1].text.strip())
create_element(root, "FieldType", first_row.find_all('td')[2].text.strip())
create_element(root, "FieldBinary", first_row.find_all('td')[4].text.strip())
create_element(root, "FieldViewable", first_row.find_all('td')[6].text.strip())
create_element(root, "ToolComment", "Default")

# Create a FieldList element
field_list = SubElement(root, "FieldList")

# A flag to track if we are still under DE055
is_de055_active = False

# Parse the remaining rows and create subfields
for row in soup.find_all('tr')[1:]:
    tds = row.find_all('td')
    cell1_text = tds[0].text.strip()

    # Check if a new DE tag is encountered
    if "DE" in cell1_text and "055" not in cell1_text:
        is_de055_active = False  # Stop processing EMVTAGs when another DE is encountered

    # Mark that we're under DE055
    if "DE055" in cell1_text:
        is_de055_active = True
        continue  # DE055 itself has been processed already

    # Only process EMVTAGs under DE055
    if is_de055_active and "EMVTAG" in cell1_text:
        field = SubElement(field_list, "Field", {"ID": "NET.1100.DE.055.TAG." + cell1_text.split('-')[-1]})
        create_element(field, "FriendlyName", tds[1].text.strip())
        create_element(field, "FieldType", tds[2].text.strip())
        emv_data = SubElement(field, "EMVData", {
            "Tag": cell1_text.split('-')[-1],
            "Name": tds[1].text.strip(),
            "Format": tds[2].text.strip()
        })
        create_element(field, "FieldBinary", tds[4].text.strip())
        create_element(field, "FieldViewable", tds[6].text.strip())
        if len(tds) > 7:
            create_element(field, "ToolComment", tds[7].text.strip())
        else:
            create_element(field, "ToolComment", "Default")
        create_element(field, "ToolCommentLevel", "INFO")
        create_element(field, "FieldList")

# Generate and print the prettified XML
xml_output = prettify_xml(root)
print(xml_output)

# Optionally, save to a file
with open("output.xml", "w") as f:
    f.write(xml_output)