async function main() {
    const { Octokit } = await import('@octokit/rest');  // Usa import dinamico
    const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });

    // Lista dei simboli dei file da eliminare
    const stockSymbols = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK.A", "V", "JPM", "JNJ",
        "WMT", "NVDA", "PYPL", "DIS", "NFLX", "NIO", "NRG", "ADBE", "INTC", "CSCO",
        "PFE", "VZ", "KO", "PEP", "MRK", "ABT", "XOM", "CVX", "T", "MCD", "NKE", "HD",
        "IBM", "CRM", "BMY", "ORCL", "ACN", "LLY", "QCOM", "HON", "COST", "SBUX",
        "MDT", "TXN", "MMM", "NEE", "PM", "BA", "UNH", "MO", "DHR", "SPGI",
        "CAT", "LOW", "MS", "GS", "AXP", "INTU", "AMGN", "GE", "FIS", "CVS",
        "TGT", "ANTM", "SYK", "BKNG", "MDLZ", "BLK", "DUK", "USB", "ISRG", "CI",
        "DE", "BDX", "NOW", "SCHW", "LMT", "ADP", "C", "PLD", "NSC", "TMUS",
        "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
        "DASHUSD", "XMRUSD", "ETCUSD", "ZECUSD", "BNBUSD", "DOGEUSD", "USDTUSD",
        "ITW", "FDX", "PNC", "SO", "APD", "ADI", "ICE", "ZTS", "TJX", "CL",
        "MMC", "EL", "GM", "CME", "EW", "AON", "D", "PSA", "AEP", "TROW"
    ];

    try {
        for (const symbol of stockSymbols) {
            const path = `${symbol.toUpperCase()}.html`;  // Nome del file basato sul simbolo

            try {
                // Ottieni il contenuto del file per avere lo SHA, necessario per l'eliminazione
                const { data: file } = await octokit.rest.repos.getContent({
                    owner: 'pammyhouse',
                    repo: 'dati-finanziari',
                    path: path,
                });

                // Elimina il file usando lo SHA per confermare l'eliminazione
                await octokit.rest.repos.deleteFile({
                    owner: 'pammyhouse',
                    repo: 'dati-finanziari',
                    path: path,
                    message: `Eliminazione automatica di ${path}`,
                    sha: file.sha,  // SHA del file per l'eliminazione
                });

                console.log(`File ${path} eliminato con successo.`);
            } catch (error) {
                if (error.status === 404) {
                    console.log(`File ${path} non trovato, potrebbe essere già eliminato.`);
                } else {
                    console.error(`Errore durante l'eliminazione di ${path}:`, error);
                }
            }
        }
    } catch (error) {
        console.error('Errore generale durante l\'eliminazione dei file:', error);
    }
}

// Avvia il processo di eliminazione
main();
