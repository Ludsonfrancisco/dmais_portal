from PIL import Image

def remove_white_bg(input_path, output_path):
    img = Image.open(input_path).convert("RGBA")
    datas = img.getdata()
    newData = []
    
    for item in datas:
        r, g, b, a = item
        # Calculate brightness (roughly)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        
        # If very close to white, make it fully transparent
        if r > 245 and g > 245 and b > 245:
            newData.append((r, g, b, 0))
        elif brightness > 220:
            # Alpha gradient based on brightness to try catching halos
            alpha = int(255 - ((brightness - 220) / 35.0) * 255)
            alpha = max(0, min(255, alpha))
            newData.append((r, g, b, alpha))
        else:
            newData.append(item)
            
    img.putdata(newData)
    img.save(output_path, "PNG")

remove_white_bg(
    r"C:\Users\ludso\.gemini\antigravity\brain\f2e4e284-c43c-4a1f-ae40-fcd309ee01ed\media__1775672446049.png", 
    r"c:\Users\ludso\Documents\dev-ia\Teste\dashboard\static\img\dmais_logo_transparent.png"
)
print("Logo processado com sucesso!")
