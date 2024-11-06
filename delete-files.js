const { Octokit } = require("@octokit/rest");

const stockSymbols = [ "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK.A", "V", "JPM", "JNJ", "WMT", "NVDA", "PYPL", "DIS", "NFLX", "NIO", "NRG", "ADBE", "INTC", "CSCO", "PFE", "VZ", "KO", "PEP", "MRK", "ABT", "XOM", "CVX", "T", "MCD", "NKE", "HD", "IBM", "CRM", "BMY", "ORCL", "ACN", "LLY", "QCOM", "HON", "COST", "SBUX", "MDT", "TXN", "MMM", "NEE", "PM", "BA", "UNH", "MO", "DHR", "SPGI", "CAT", "LOW", "MS", "GS", "AXP", "INTU", "AMGN", "GE", "FIS", "CVS", "TGT", "ANTM", "SYK", "BKNG", "MDLZ", "BLK", "DUK", "USB", "ISRG", "CI", "DE", "BDX", "NOW", "SCHW", "LMT", "ADP", "C", "PLD", "NSC", "TMUS", "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "DASHUSD", "XMRUSD", "ETCUSD", "ZECUSD", "BNBUSD", "DOGEUSD", "USDTUSD", "ITW", "FDX", "PNC", "SO", "APD", "ADI", "ICE", "ZTS", "TJX", "CL", "MMC", "EL", "GM", "CME", "EW", "AON", "D", "PSA", "AEP", "TROW" ];

const octokit = new Octokit({
  auth: process.env.GITHUB_TOKEN
});

const owner = 'pammyhouse';
const repo = 'dati-finanziari';

async function deleteFiles() {
  const failedFiles = [];
  const batchSize = 5; // Gruppi di 5 file alla volta

  for (let i = 0; i < stockSymbols.length; i += batchSize) {
    const batch = stockSymbols.slice(i, i + batchSize);

    for (const symbol of batch) {
      const path = `${symbol.toUpperCase()}.html`;

      try {
        // Ottieni il contenuto del file per verificarne l'esistenza
        const file = await octokit.repos.getContent({
          owner,
          repo,
          path
        });

        if (file) {
          await octokit.repos.deleteFile({
            owner,
            repo,
            path,
            message: `Deleting File ${path}`,
            sha: file.data.sha
          });
          console.log(`File eliminato: ${path}`);
        }
      } catch (error) {
        console.error(`Errore durante l'eliminazione del file ${path}:`, error);
        failedFiles.push(path);
      }
    }

    // Pausa tra i batch
    await new Promise(resolve => setTimeout(resolve, 500));
  }

  if (failedFiles.length > 0) {
    console.error('File non eliminati:', failedFiles);
  } else {
    console.log('Tutti i file sono stati eliminati correttamente.');
  }
}

// Esegui la funzione di eliminazione
deleteFiles().catch(error => console.error('Errore generale:', error));
