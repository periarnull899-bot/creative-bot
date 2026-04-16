import os
import logging
import requests
import json
import time
import io
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
REPLICATE_TOKEN = os.environ.get("REPLICATE_TOKEN", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")

# Stockage en mémoire
user_sessions = {}
user_history = {}
user_favorites = {}

STYLES_IMAGE = {
    "🎨 Artistique": "artistic, painterly, expressive brushstrokes, vivid colors",
    "📸 Réaliste": "photorealistic, ultra detailed, 8k, professional photography",
    "🎬 Cinématique": "cinematic, movie still, dramatic lighting, anamorphic lens",
    "🌸 Anime": "anime style, manga, japanese animation, vibrant",
    "🏛️ Renaissance": "renaissance painting, classical art, oil on canvas, masterpiece",
    "🌆 Cyberpunk": "cyberpunk, neon lights, futuristic city, dystopian",
    "🧸 3D Cartoon": "3D render, pixar style, cute, cartoon, colorful",
    "⚡ Sans style": ""
}

STYLES_VIDEO = {
    "🎬 Cinématique": "cinematic camera movement, dramatic lighting, film quality",
    "📱 Social Media": "dynamic, engaging, trendy, social media style",
    "🎭 Dramatique": "dramatic, emotional, powerful storytelling",
    "🌊 Fluide": "smooth motion, fluid transitions, elegant movement",
    "⚡ Sans style": ""
}

MODELES_IMAGE = {
    "⚡ Flux (Ultra réaliste)": "black-forest-labs/flux-schnell",
    "🎨 SDXL (Polyvalent)": "stability-ai/sdxl",
    "🤗 HuggingFace (Gratuit)": "huggingface"
}

MODELES_VIDEO = {
    "🎬 Seedance (ByteDance)": "bytedance/seedance-1-lite",
    "🎥 Kling (Cinématique)": "klingai/kling-v1-5-pro",
    "🆓 Wan 2.1 (Gratuit)": "wavespeedai/wan-2.1-t2v-480p"
}

def send_message(chat_id, text, keyboard=None, remove_keyboard=False):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        payload["reply_markup"] = {
            "keyboard": keyboard,
            "one_time_keyboard": True,
            "resize_keyboard": True
        }
    elif remove_keyboard:
        payload["reply_markup"] = {"remove_keyboard": True}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"send_message error: {e}")

def send_photo_url(chat_id, photo_url, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        requests.post(url, json={"chat_id": chat_id, "photo": photo_url, "caption": caption}, timeout=10)
    except Exception as e:
        logger.error(f"send_photo error: {e}")

def send_video_url(chat_id, video_url, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVideo"
    try:
        requests.post(url, json={"chat_id": chat_id, "video": video_url, "caption": caption}, timeout=10)
    except Exception as e:
        logger.error(f"send_video error: {e}")

def send_photo_bytes(chat_id, photo_bytes, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        requests.post(url, data={"chat_id": chat_id, "caption": caption},
                      files={"photo": ("image.jpg", photo_bytes)}, timeout=30)
    except Exception as e:
        logger.error(f"send_photo_bytes error: {e}")

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(url, params=params, timeout=35)
        return resp.json()
    except:
        return {"ok": False, "result": []}

def get_file_url(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile"
    resp = requests.get(url, params={"file_id": file_id}, timeout=10)
    data = resp.json()
    file_path = data["result"]["file_path"]
    return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

def improve_prompt(prompt, mode="image"):
    """Améliore automatiquement le prompt via HuggingFace"""
    try:
        system = "image cinématique ultra réaliste" if mode == "image" else "vidéo cinématique courte"
        improved = f"{prompt}, ultra detailed, high quality, professional {system}, masterpiece"
        return improved
    except:
        return prompt

def save_to_history(chat_id, type_, prompt, result_url, model):
    if chat_id not in user_history:
        user_history[chat_id] = []
    user_history[chat_id].append({
        "type": type_,
        "prompt": prompt[:50],
        "url": result_url,
        "model": model,
        "date": datetime.now().strftime("%d/%m %H:%M")
    })
    if len(user_history[chat_id]) > 20:
        user_history[chat_id] = user_history[chat_id][-20:]

def save_to_favorites(chat_id, url, prompt):
    if chat_id not in user_favorites:
        user_favorites[chat_id] = []
    user_favorites[chat_id].append({
        "url": url,
        "prompt": prompt[:50],
        "date": datetime.now().strftime("%d/%m %H:%M")
    })

def generate_image_replicate(prompt, model_id):
    headers = {
        "Authorization": f"Bearer {REPLICATE_TOKEN}",
        "Content-Type": "application/json"
    }
    input_data = {"prompt": prompt, "num_outputs": 1}
    if "sdxl" in model_id:
        input_data["width"] = 1024
        input_data["height"] = 1024

    resp = requests.post(
        f"https://api.replicate.com/v1/models/{model_id}/predictions",
        headers=headers,
        json={"input": input_data},
        timeout=30
    )
    if resp.status_code not in [200, 201]:
        resp2 = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers=headers,
            json={"version": model_id, "input": input_data},
            timeout=30
        )
        prediction = resp2.json()
    else:
        prediction = resp.json()

    prediction_id = prediction.get("id")
    if not prediction_id:
        return None

    for _ in range(60):
        time.sleep(3)
        poll = requests.get(
            f"https://api.replicate.com/v1/predictions/{prediction_id}",
            headers=headers, timeout=10
        ).json()
        status = poll.get("status")
        if status == "succeeded":
            output = poll.get("output")
            if isinstance(output, list):
                return output[0]
            return output
        elif status == "failed":
            return None
    return None

def generate_image_hf(prompt):
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    api_url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
    resp = requests.post(api_url, headers=headers,
                         json={"inputs": prompt}, timeout=60)
    if resp.status_code == 200:
        return resp.content
    return None

def generate_video_replicate(prompt, model_id, image_url=None):
    headers = {
        "Authorization": f"Bearer {REPLICATE_TOKEN}",
        "Content-Type": "application/json"
    }
    input_data = {"prompt": prompt}
    if image_url and "kling" in model_id:
        input_data["image"] = image_url

    resp = requests.post(
        "https://api.replicate.com/v1/predictions",
        headers=headers,
        json={"model": model_id, "input": input_data},
        timeout=30
    )
    prediction = resp.json()
    prediction_id = prediction.get("id")
    if not prediction_id:
        return None

    for _ in range(120):
        time.sleep(5)
        poll = requests.get(
            f"https://api.replicate.com/v1/predictions/{prediction_id}",
            headers=headers, timeout=10
        ).json()
        status = poll.get("status")
        if status == "succeeded":
            output = poll.get("output")
            if isinstance(output, list):
                return output[0]
            return output
        elif status == "failed":
            return None
    return None

def show_main_menu(chat_id):
    send_message(chat_id, "🎨 *CreativeBot — Menu Principal*\n\nQue veux-tu créer ?", keyboard=[
        ["🖼️ Générer une image", "🎬 Générer une vidéo"],
        ["🎥 Image → Vidéo", "✨ Génération rapide"],
        ["📚 Mon historique", "⭐ Mes favoris"],
        ["ℹ️ Aide"]
    ])

def handle_message(chat_id, text, photo_file_id=None):
    session = user_sessions.get(chat_id, {"step": "menu"})
    step = session.get("step", "menu")

    # Commandes globales
    if text in ["/start", "/menu", "🏠 Menu"]:
        user_sessions[chat_id] = {"step": "menu"}
        show_main_menu(chat_id)
        return

    if text == "ℹ️ Aide":
        send_message(chat_id,
            "ℹ️ *Aide CreativeBot*\n\n"
            "🖼️ *Image* → Génère une image IA\n"
            "🎬 *Vidéo* → Génère une vidéo IA\n"
            "🎥 *Image→Vidéo* → Anime une photo\n"
            "✨ *Rapide* → Image instantanée\n"
            "📚 *Historique* → Tes 20 dernières créations\n"
            "⭐ *Favoris* → Tes sauvegardes\n\n"
            "💡 *Astuce* : Le prompt est amélioré automatiquement !",
            keyboard=[["🏠 Menu"]]
        )
        return

    if text == "📚 Mon historique":
        history = user_history.get(chat_id, [])
        if not history:
            send_message(chat_id, "📚 Ton historique est vide.\n\nCommence par générer une image ou vidéo !", keyboard=[["🏠 Menu"]])
        else:
            msg = "📚 *Tes dernières créations :*\n\n"
            for i, item in enumerate(reversed(history[-10:]), 1):
                emoji = "🖼️" if item["type"] == "image" else "🎬"
                msg += f"{emoji} *{i}.* {item['prompt']}...\n📅 {item['date']} — {item['model']}\n\n"
            send_message(chat_id, msg, keyboard=[["🏠 Menu"]])
        return

    if text == "⭐ Mes favoris":
        favs = user_favorites.get(chat_id, [])
        if not favs:
            send_message(chat_id, "⭐ Aucun favori sauvegardé.\n\nAprès une génération, tape /fav pour sauvegarder !", keyboard=[["🏠 Menu"]])
        else:
            msg = "⭐ *Tes favoris :*\n\n"
            for i, fav in enumerate(favs, 1):
                msg += f"*{i}.* {fav['prompt']}...\n📅 {fav['date']}\n\n"
            send_message(chat_id, msg, keyboard=[["🏠 Menu"]])
        return

    if text == "/fav":
        last = (user_history.get(chat_id) or [{}])[-1]
        if last.get("url"):
            save_to_favorites(chat_id, last["url"], last.get("prompt", ""))
            send_message(chat_id, "⭐ Ajouté à tes favoris !", keyboard=[["🏠 Menu"]])
        else:
            send_message(chat_id, "Génère d'abord une image ou vidéo !", keyboard=[["🏠 Menu"]])
        return

    # ─── GÉNÉRATION RAPIDE ───────────────────────────────
    if text == "✨ Génération rapide":
        user_sessions[chat_id] = {"step": "quick_prompt"}
        send_message(chat_id,
            "✨ *Génération rapide*\n\nEntre ton prompt directement — je génère avec Flux !\n\n"
            "_Ex: Un lion majestueux dans la savane au coucher du soleil_",
            remove_keyboard=True
        )
        return

    if step == "quick_prompt":
        prompt = improve_prompt(text, "image")
        send_message(chat_id, f"⚡ Génération en cours...\n✨ Prompt amélioré: _{prompt}_", remove_keyboard=True)
        img_bytes = generate_image_hf(prompt)
        if img_bytes:
            send_photo_bytes(chat_id, img_bytes, f"✨ {text[:50]}")
            save_to_history(chat_id, "image", text, "hf_generated", "HuggingFace Flux")
            send_message(chat_id, "✅ Généré ! Tape /fav pour sauvegarder.", keyboard=[
                ["🏠 Menu", "✨ Génération rapide"]
            ])
        else:
            send_message(chat_id, "❌ Erreur de génération. Réessaie !", keyboard=[["🏠 Menu"]])
        user_sessions[chat_id] = {"step": "menu"}
        return

    # ─── GÉNÉRATION IMAGE ─────────────────────────────────
    if text == "🖼️ Générer une image":
        user_sessions[chat_id] = {"step": "image_model"}
        send_message(chat_id, "🖼️ *Génération d'image*\n\nChoisis ton modèle IA :", keyboard=[
            ["⚡ Flux (Ultra réaliste)", "🎨 SDXL (Polyvalent)"],
            ["🤗 HuggingFace (Gratuit)"],
            ["🏠 Menu"]
        ])
        return

    if step == "image_model" and text in MODELES_IMAGE:
        session["model"] = text
        session["model_id"] = MODELES_IMAGE[text]
        session["step"] = "image_style"
        user_sessions[chat_id] = session
        send_message(chat_id, "🎨 *Choisis un style :*", keyboard=[
            ["🎨 Artistique", "📸 Réaliste", "🎬 Cinématique"],
            ["🌸 Anime", "🏛️ Renaissance", "🌆 Cyberpunk"],
            ["🧸 3D Cartoon", "⚡ Sans style"],
            ["🏠 Menu"]
        ])
        return

    if step == "image_style" and text in STYLES_IMAGE:
        session["style"] = STYLES_IMAGE[text]
        session["style_name"] = text
        session["step"] = "image_prompt"
        user_sessions[chat_id] = session
        send_message(chat_id,
            f"✍️ *Entre ton prompt :*\n\nStyle sélectionné: {text}\n\n"
            "_Ex: Une ville futuriste sous la pluie, reflets sur le sol mouillé_",
            remove_keyboard=True
        )
        return

    if step == "image_prompt":
        raw_prompt = text
        style = session.get("style", "")
        full_prompt = improve_prompt(f"{raw_prompt}, {style}" if style else raw_prompt, "image")
        model_name = session.get("model", "HuggingFace")
        model_id = session.get("model_id", "huggingface")

        send_message(chat_id,
            f"🎨 Génération en cours...\n"
            f"🤖 Modèle: *{model_name}*\n"
            f"✨ Prompt amélioré: _{full_prompt[:100]}_\n\n"
            f"⏳ Patience, ça peut prendre 30-60 secondes...",
            remove_keyboard=True
        )

        result_url = None
        img_bytes = None

        if model_id == "huggingface":
            img_bytes = generate_image_hf(full_prompt)
        else:
            result_url = generate_image_replicate(full_prompt, model_id)

        if img_bytes:
            send_photo_bytes(chat_id, img_bytes, f"🖼️ {raw_prompt[:50]}")
            save_to_history(chat_id, "image", raw_prompt, "bytes", model_name)
            send_message(chat_id, "✅ Image générée ! Tape /fav pour sauvegarder.", keyboard=[
                ["🖼️ Générer une image", "🎬 Générer une vidéo"],
                ["🏠 Menu"]
            ])
        elif result_url:
            send_photo_url(chat_id, result_url, f"🖼️ {raw_prompt[:50]}")
            save_to_history(chat_id, "image", raw_prompt, result_url, model_name)
            send_message(chat_id, "✅ Image générée ! Tape /fav pour sauvegarder.", keyboard=[
                ["🖼️ Générer une image", "🎬 Générer une vidéo"],
                ["🏠 Menu"]
            ])
        else:
            send_message(chat_id, "❌ Erreur de génération. Vérifie tes crédits Replicate et réessaie.", keyboard=[["🏠 Menu"]])

        user_sessions[chat_id] = {"step": "menu"}
        return

    # ─── GÉNÉRATION VIDÉO ─────────────────────────────────
    if text == "🎬 Générer une vidéo":
        user_sessions[chat_id] = {"step": "video_model"}
        send_message(chat_id, "🎬 *Génération de vidéo*\n\nChoisis ton modèle :", keyboard=[
            ["🎬 Seedance (ByteDance)", "🎥 Kling (Cinématique)"],
            ["🆓 Wan 2.1 (Gratuit)"],
            ["🏠 Menu"]
        ])
        return

    if step == "video_model" and text in MODELES_VIDEO:
        session["model"] = text
        session["model_id"] = MODELES_VIDEO[text]
        session["step"] = "video_style"
        user_sessions[chat_id] = session
        send_message(chat_id, "🎭 *Choisis un style vidéo :*", keyboard=[
            ["🎬 Cinématique", "📱 Social Media"],
            ["🎭 Dramatique", "🌊 Fluide"],
            ["⚡ Sans style"],
            ["🏠 Menu"]
        ])
        return

    if step == "video_style" and text in STYLES_VIDEO:
        session["style"] = STYLES_VIDEO[text]
        session["step"] = "video_prompt"
        user_sessions[chat_id] = session
        send_message(chat_id,
            f"✍️ *Entre ton prompt vidéo :*\n\nStyle: {text}\n\n"
            "_Ex: Un aigle volant au-dessus des montagnes enneigées_",
            remove_keyboard=True
        )
        return

    if step == "video_prompt":
        raw_prompt = text
        style = session.get("style", "")
        full_prompt = improve_prompt(f"{raw_prompt}, {style}" if style else raw_prompt, "video")
        model_name = session.get("model", "Wan 2.1")
        model_id = session.get("model_id", MODELES_VIDEO["🆓 Wan 2.1 (Gratuit)"])

        send_message(chat_id,
            f"🎬 Génération vidéo en cours...\n"
            f"🤖 Modèle: *{model_name}*\n"
            f"✨ Prompt: _{full_prompt[:100]}_\n\n"
            f"⏳ La vidéo prend 2-5 minutes...",
            remove_keyboard=True
        )

        result_url = generate_video_replicate(full_prompt, model_id)

        if result_url:
            send_video_url(chat_id, result_url, f"🎬 {raw_prompt[:50]}")
            save_to_history(chat_id, "video", raw_prompt, result_url, model_name)
            send_message(chat_id, "✅ Vidéo générée ! Tape /fav pour sauvegarder.", keyboard=[
                ["🖼️ Générer une image", "🎬 Générer une vidéo"],
                ["🏠 Menu"]
            ])
        else:
            send_message(chat_id, "❌ Erreur. Vérifie tes crédits Replicate et réessaie.", keyboard=[["🏠 Menu"]])

        user_sessions[chat_id] = {"step": "menu"}
        return

    # ─── IMAGE → VIDÉO ───────────────────────────────────
    if text == "🎥 Image → Vidéo":
        user_sessions[chat_id] = {"step": "img2vid_upload"}
        send_message(chat_id,
            "🎥 *Image → Vidéo*\n\nEnvoie-moi une photo et je la transforme en vidéo !\n\n"
            "📸 Envoie ton image maintenant...",
            remove_keyboard=True
        )
        return

    if step == "img2vid_upload" and photo_file_id:
        image_url = get_file_url(photo_file_id)
        session["image_url"] = image_url
        session["step"] = "img2vid_prompt"
        user_sessions[chat_id] = session
        send_message(chat_id,
            "✅ Photo reçue !\n\n✍️ *Entre une description du mouvement voulu :*\n\n"
            "_Ex: La personne sourit et tourne la tête doucement_",
            remove_keyboard=True
        )
        return

    if step == "img2vid_prompt":
        raw_prompt = text
        full_prompt = improve_prompt(raw_prompt, "video")
        image_url = session.get("image_url")

        send_message(chat_id,
            f"🎥 Animation en cours...\n"
            f"✨ _{full_prompt[:100]}_\n\n"
            f"⏳ 2-5 minutes...",
            remove_keyboard=True
        )

        result_url = generate_video_replicate(
            full_prompt,
            MODELES_VIDEO["🎥 Kling (Cinématique)"],
            image_url=image_url
        )

        if result_url:
            send_video_url(chat_id, result_url, f"🎥 {raw_prompt[:50]}")
            save_to_history(chat_id, "video", raw_prompt, result_url, "Kling")
            send_message(chat_id, "✅ Vidéo générée ! Tape /fav pour sauvegarder.", keyboard=[
                ["🖼️ Générer une image", "🎬 Générer une vidéo"],
                ["🏠 Menu"]
            ])
        else:
            send_message(chat_id, "❌ Erreur. Réessaie !", keyboard=[["🏠 Menu"]])

        user_sessions[chat_id] = {"step": "menu"}
        return

    # Menu par défaut
    show_main_menu(chat_id)

def main():
    logger.info("CreativeBot demarre !")
    offset = None
    while True:
        updates = get_updates(offset)
        if not updates.get("ok"):
            time.sleep(5)
            continue
        for update in updates.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "")
            photo = message.get("photo")
            photo_file_id = photo[-1]["file_id"] if photo else None

  
