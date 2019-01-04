$(document).ready(function() {
  $(window).on("scroll", function() {
    $(".navbar").toggleClass("compressed", $(window).scrollTop() >= 20);
  });
});


$(function(){
    /* Callback from main message view when a message is picked in dropdown */
    $('#thread_select').change(function(e) {
	document.location.href = '/message-id/' + $(this).val();
    });


    /*
     * For flat message view, redirect to the anchor of the messageid we're watching,
     * unless we happen to be the first one.
     */
    $('#flatMsgSubject[data-isfirst=False]').each(function(i, e) {
	if (document.location.href.indexOf('#') < 0) {
	    document.location.href = document.location.href + '#' + $(e).data('msgid');
	    return;
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
