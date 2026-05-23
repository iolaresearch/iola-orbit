export default async function handler(req, res) {
    const response = await fetch(`${process.env.IOLA_ORB_API_URL}/tles`);
    const data = await response.text();
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Content-Type", "text/plain");
    res.send(data);
}
