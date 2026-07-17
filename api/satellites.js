export default async function handler(req, res) {
    const response = await fetch(`${process.env.IOLA_ORB_API_URL}/catalog`);
    if (!response.ok) {
        res.status(response.status).end();
        return;
    }
    const data = await response.text();
    res.setHeader("Cache-Control", "public, max-age=60");
    res.setHeader("Content-Type", "application/json");
    res.send(data);
}
