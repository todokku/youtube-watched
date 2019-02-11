if (!document.querySelector("#takeout-section").dataset.full) {
document.querySelector("#takeout-setup").classList.remove("hidden");
} else {
    toggleElementVisibility("takeout-setup-button", "takeout-setup", "Cancel", "takeout-input");
}

let progressMsg = document.querySelector("#progress-msg");
let progressBar = document.querySelector("#progress-bar");
let progressBarPercentage = document.querySelector("#progress-bar-text span");
let progressUnfinishedDBProcessWarning = document.querySelector("#wait-for-db");
let takeoutSubmit = document.querySelector("#takeout-form");
let takeoutSubmitButton = takeoutSubmit.querySelector("input[type='submit']");
let takeoutCancelButton = document.querySelector("#takeout-cancel-button");

function processTakeout(event) {
    event.preventDefault();
    let takeoutDirectoryVal = document.querySelector("#takeout-input").value;
    let progress = new EventSource("/db_progress_stream");
    console.log("Progress at start:", progress.readyState);

    function closeEventSource() {
        progress.close();
    }

    function cleanUpAfterTakeoutInsertion() {
        takeoutSubmitButton.removeAttribute('disabled');
        takeoutCancelButton.style.display = "none";
        progress.close();
        window.removeEventListener('beforeunload', closeEventSource);
    }

    function cleanUpProgressBar() {
        document.querySelector("#progress-bar-container").style.display = "none";
        takeoutCancelButton.style.display = "inline-block";
        progressBar.style.width = "0%";
        progressBarPercentage.innerHTML = "0%";
        progressMsg.innerHTML = "";
    }

    function showProgress() {
        if (anAJAX.readyState === 4 && anAJAX.status === 200) {
            if (anAJAX.responseText.indexOf("Wait for") !== -1) {
                if (progressUnfinishedDBProcessWarning.innerHTML === "") {
                    progressUnfinishedDBProcessWarning.innerHTML = anAJAX.responseText;
                    setTimeout(function() {progressUnfinishedDBProcessWarning.innerHTML = "";}, 3000);
                    closeEventSource();
                }
            } else {
                cleanUpProgressBar();
                document.querySelector("#progress-bar-container").style.display = "flex";
                takeoutSubmitButton.setAttribute('disabled', 'true');

                window.addEventListener('beforeunload', closeEventSource);
                progress.onmessage = function (event) {
                    if (event.data.length < 6) {
                        let progressVal = event.data + "%";
                        progressBar.style.width = progressVal;
                        progressBarPercentage.innerHTML = progressVal;
                    } else {
                        progressMsg.innerHTML = event.data;
                        if (event.data.indexOf("records_processed") !== -1) {
                            progressBar.style.width = "100%";
                            progressBarPercentage.innerHTML = "100%";
                            let msgJSON = JSON.parse(event.data);
                            /** @namespace  msgJSON.records_processed **/
                            /** @namespace msgJSON.records_inserted **/
                            /** @namespace msgJSON.records_updated **/
                            /** @namespace msgJSON.records_in_db **/
                            /** @namespace  msgJSON.dead_records */
                            /** @namespace msgJSON.failed_api_requests **/
                            let msgString = ("Records processed: " + msgJSON.records_processed +
                                "<br>Inserted: " + msgJSON.records_inserted +
                                "<br>Updated: " + msgJSON.records_updated +
                                "<br>Total in the database: " + msgJSON.records_in_db);
                            // noinspection JSValidateTypes
                            if (msgJSON.failed_api_requests !== 0) {
                                msgString += ("<br>Failed API requests: " + msgJSON.failed_api_requests +
                                    " (run this again to attempt these 1-2 more times.)")
                            }
                            // noinspection JSValidateTypes
                            if (msgJSON.dead_records !== 0) {
                                msgString += "<br>Videos with no identifying info: " +
                                    msgJSON.dead_records + " (added as unknown)"
                            }
                            progressMsg.innerHTML = msgString;
                            console.log('The state #2:', progress.readyState);
                            cleanUpAfterTakeoutInsertion();
                            console.log('The state #3:', progress.readyState);

                        } else if (event.data.indexOf("Error") !== -1) {
                            console.log("This is throwing an error!");
                            progressMsg.style.color = 'red';
                            console.log('The state #2:', progress.readyState);
                            cleanUpAfterTakeoutInsertion();
                            console.log('The state #3:', progress.readyState);
                        }
                    }
                };
            }
        }
    }

    takeoutCancelButton.onclick = function () {
        let cancelAJAX = new XMLHttpRequest();
        cancelAJAX.open("POST", "cancel_db_process");
        cancelAJAX.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
        function cancelTakeout() {
            if (cancelAJAX.readyState === 4 && cancelAJAX.status === 200) {
                cleanUpAfterTakeoutInsertion(progress);
                cleanUpProgressBar();
            }
        }
        cancelAJAX.addEventListener("readystatechange", cancelTakeout);
        cancelAJAX.send();
    };

    let anAJAX = new XMLHttpRequest();
    anAJAX.open("POST", "/convert_takeout");
    anAJAX.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
    anAJAX.addEventListener("readystatechange", showProgress);
    anAJAX.send("takeout-dir=" + takeoutDirectoryVal);
    // takeoutSubmitButton.removeEventListener("submit", processTakeout);

}
takeoutSubmit.addEventListener("submit", processTakeout);