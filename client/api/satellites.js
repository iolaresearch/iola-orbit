export default async function handler(req, res) {
    const response = await fetch(`${process.env.IOLA_ORB_API_URL}/satellites`);
    const data = await response.json();
    res.setHeader("Cache-Control", "no-store");
    res.json(data);
}
