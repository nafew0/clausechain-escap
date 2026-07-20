from rest_framework.pagination import PageNumberPagination


class WorkspacePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def response_payload(self, data, **extra):
        return {
            **extra,
            "count": self.page.paginator.count,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        }
