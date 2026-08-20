"""One-off: attach on-brand AI cover art to the 12 flagship stations.
Sets `flagship_art` (shell summary prefers it over the ui-avatars favicon).
"""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient

BASE = "https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/"
ART = {
    "beat-978-uae": "763d1098ee569aaedf1bfbb6c9916af709ef731d0be1185f68f57aee80239db9.jpeg",
    "beat-anthems": "53f7fdccbde973b62b621a49adc3cb81eef8ad7192e0d229a5ddcb68d3c717bf.jpeg",
    "big-1062-uae": "4255ce1f27f15fff9a8f0e6e77e4bf4119ab5fa239ac13f9fc4ba84cf000afab.jpeg",
    "big-melodies": "e41edd0d6e390fda10daa3c6f0b251d7e335a292582f829b59e0536d6faeded6.jpeg",
    "chilled-luv": "9fab8bfba1e9562948bbd3e6f94b0c379ca749c7ae34cd8d95e06cfee531ab77.jpeg",
    "funasia-fm-dallas": "beec2c19972c778d35ef860ffe1f70ce39ecb023a100d0923d30b4b4108dd88f.jpeg",
    "luv-1071-uae": "c8f06dca3d0f4a5fd9207b52e739a3d8c259291d9afde169900bc4bcba60346a.jpeg",
    "luv-legends": "c197ee265347df1c36111bea750a3d8ed14da34a9bdbcd5e01e7494a1e0909a2.jpeg",
    "radio-caravan-dallas": "7f5852b8ed8ba72a8919bab6fe5698b92c5b703014f81d707d1dfb16cc24022d.jpeg",
    "radio-sangam-dallas": "664c06eef1a604601cc4ab3063c5bed0c0cc2d2968539e47b3ee2ba0c776c4f9.jpeg",
    "talk-1003-uae": "0d00254424c15f1aa7a26f531ada95decd508d7636b845ccb4844b53ee6a4706.jpeg",
    "urban-beat": "2a17d1b309e5771a69f750dd6b231dccaae041333d7982db37b378a737dbf57b.jpeg",
}


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    n = 0
    for slug, fname in ART.items():
        r = await db.imported_radio_stations.update_one(
            {"flagship_slug": slug}, {"$set": {"flagship_art": BASE + fname}})
        n += r.modified_count
        print(slug, "->", r.matched_count, r.modified_count)
    print("updated", n)


if __name__ == "__main__":
    asyncio.run(main())
