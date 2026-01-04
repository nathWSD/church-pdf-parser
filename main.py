from fastapi import FastAPI, HTTPException, Body
from pypdf import PdfReader
import requests
import io
import uvicorn
import base64

app = FastAPI()

def reconstruct_layout(elements):
    """
    Sorts elements by coordinates and inserts newlines/paragraphs based on gaps.
    """
    if not elements: return []

    # Sort: Primary = Y (Desc/Top to Bottom), Secondary = X (Asc/Left to Right)
    elements.sort(key=lambda k: (-k["y"], k["x"]))

    final_items = []
    current_text_buffer = []
    last_y = None
    last_x = None

    for el in elements:
        # If it's an image, flush text buffer and add image
        if el["type"] == "image":
            if current_text_buffer:
                final_items.append({"type": "text", "value": "".join(current_text_buffer)})
                current_text_buffer = []
            
            final_items.append({"type": "image", "value": el["val"]}) # val contains base64
            last_y = None 
            continue

        # Handle Text
        text = el["val"]
        curr_y = el["y"]
        curr_x = el["x"]

        if last_y is not None:
            gap = last_y - curr_y
            
            if gap > 20: 
                current_text_buffer.append("\n\n")
            elif gap > 5:
                current_text_buffer.append("\n")
            else:
                if last_x is not None and (curr_x - last_x) > 2:
                    current_text_buffer.append(" ")

        current_text_buffer.append(text)
        last_y = curr_y
        last_x = curr_x + (len(text) * 4) 

    if current_text_buffer:
        final_items.append({"type": "text", "value": "".join(current_text_buffer)})

    return final_items

@app.get("/")
def home():
    return {"status": "PDF Parser Online"}

@app.post("/parse-pdf")
def parse_pdf(payload: dict = Body(...)):
    file_url = payload.get("file_url")
    if not file_url:
        raise HTTPException(status_code=400, detail="No file_url provided")

    print(f"Downloading: {file_url}")
    
    try:
        response = requests.get(file_url)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to download PDF: {response.status_code}")

        pdf_file = io.BytesIO(response.content)
        reader = PdfReader(pdf_file)
        
        output = {
            "page_count": len(reader.pages),
            "pages": []
        }

        for i, page in enumerate(reader.pages):
            page_elements = []

            # --- 1. Get XObjects (Images) for the page ---
            page_xobjects = {}
            if '/Resources' in page and '/XObject' in page['/Resources']:
                page_xobjects = page['/Resources']['/XObject'].get_object()

            # --- 2. Visitor for Text ---
            def visitor_text(text, cm, tm, fontDict, fontSize):
                if text and text.strip():
                    page_elements.append({
                        "y": tm[5],
                        "x": tm[4],
                        "type": "text",
                        "val": text
                    })

            # --- 3. Visitor for Images (MISSING PART ADDED) ---
            def visitor_body(op, args, cm, tm):
                if op == b"Do" and len(args) > 0:
                    try:
                        xobj_name = args[0]
                        if xobj_name in page_xobjects:
                            xobj = page_xobjects[xobj_name]
                            if xobj['/Subtype'] == '/Image':
                                data = xobj.get_data()
                                # Convert raw bytes to Base64 string for JSON transport
                                b64 = base64.b64encode(data).decode('utf-8')
                                
                                page_elements.append({
                                    "y": cm[5],
                                    "x": cm[4],
                                    "type": "image",
                                    "val": b64
                                })
                    except Exception as e:
                        print(f"Image extract error: {e}")

            # Extract both text and images
            page.extract_text(
                visitor_text=visitor_text,
                visitor_operand_before=visitor_body
            )

            structured_items = reconstruct_layout(page_elements)

            output["pages"].append({
                "page": i + 1,
                "items": structured_items
            })

        return output

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)