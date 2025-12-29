from fastapi import FastAPI, HTTPException, Body
from pypdf import PdfReader
import requests
import io
import uvicorn

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
        # 1. Download File
        response = requests.get(file_url)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to download PDF: {response.status_code}")

        # 2. Parse PDF
        pdf_file = io.BytesIO(response.content)
        reader = PdfReader(pdf_file)
        
        output = {
            "page_count": len(reader.pages),
            "pages": []
        }

        # 3. Extract Text & Coords
        for i, page in enumerate(reader.pages):
            page_elements = []

            def visitor_text(text, cm, tm, fontDict, fontSize):
                if text and text.strip():
                    page_elements.append({
                        "y": tm[5],
                        "x": tm[4],
                        "type": "text",
                        "val": text
                    })

            # Extract
            page.extract_text(visitor_text=visitor_text)

            # Reconstruct
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