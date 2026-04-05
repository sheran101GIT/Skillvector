document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('candidateSearch');
    const searchResults = document.getElementById('searchResults');

    if (searchInput) {
        searchInput.addEventListener('input', debounce(function (e) {
            const query = e.target.value;
            const jobId = e.target.dataset.jobId;

            if (query.length < 2) {
                searchResults.innerHTML = '';
                return;
            }

            fetch(`/api/search?q=${encodeURIComponent(query)}&job_id=${jobId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        console.error(data.error);
                        return;
                    }
                    displayResults(data);
                });
        }, 300));
    }

    function displayResults(results) {
        if (results.length === 0) {
            searchResults.innerHTML = '<p>No matching candidates found.</p>';
            return;
        }

        const html = results.map(c => `
            <div class="search-result-item">
                <a href="/candidates/${c.id}">${c.name}</a>
                <span class="score">${Math.round(c.match_score * 100)}% Match</span>
            </div>
        `).join('');

        searchResults.innerHTML = html;
    }

    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
});
