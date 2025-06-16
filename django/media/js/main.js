document.addEventListener('DOMContentLoaded', (event) => {
    const threadselect = document.getElementById('thread_select');
    if (threadselect) {
            threadselect.addEventListener('change', (event) => {
	        document.location.href = '/message-id/' + event.target.value;
                event.preventDefault();
            });
    }

    /* Callback for viewing protected versions */
    const postlinkform = document.getElementById('mail_other_options_form');
    document.querySelectorAll('a.post-link').forEach((link) => {
        link.addEventListener('click', (event) => {
            postlinkform.action = event.target.dataset.ref;
            postlinkform.submit();
            event.preventDefault();
        });
    });


    /*
     * For flat message view, redirect to the anchor of the messageid we're watching,
     * unless we happen to be the first one.
     */
    document.querySelectorAll('#flatMsgSubject[data-isfirst=False]').forEach((e) => {
	if (document.location.href.indexOf('#') < 0) {
            document.location.href = document.location.href + '#' + e.dataset.msgid;
        }
    });
});



/*
 * Google analytics
 */
var _gaq = _gaq || [];
_gaq.push(['_setAccount', 'UA-1345454-1']);
_gaq.push(['_trackPageview']);
(function() {
    var ga = document.createElement('script'); ga.type = 'text/javascript'; ga.async = true;
    ga.src = ('https:' == document.location.protocol ? 'https://ssl' : 'http://www') + '.google-analytics.com/ga.js';
    var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(ga, s);
})();
